# Detection Console

Aceasta este soluția mea pentru tema tehnică de Senior Software Engineer: o platformă web simplificată pentru
managementul detecțiilor de securitate.

Pe scurt, aplicația face următoarele:
- primește incidente prin HTTP;
- le corelează cu o bază de semnături;
- le calculează prioritatea din importanța clientului și prioritatea semnăturii;
- le pune într-o coadă din care analiștii le preiau și le rezolvă.

Mai jos găsiți:
1. cum o porniți în câteva minute;
2. ce vă recomand să încercați;
3. unde să vă uitați în cod pentru fiecare criteriu de evaluare;
4. deciziile pe care le-am luat și de ce.

**Stack:** Python 3.12+ cu FastAPI, PostgreSQL 17 (SQL scris direct cu `psycopg`, fără ORM), UI în HTML/JS simplu, fără pas de build.

---

## 1. Pornirea aplicației

Cel mai simplu e cu Docker. Din folderul proiectului rulați:

```bash
docker compose up --build
```

Comanda pornește Postgres și aplicația. Deschideți apoi **http://localhost:8000**. La prima pornire, baza de date se populează automat cu clienți, semnături și câteva incidente demo, deci aveți ce explora din prima.

Vă puteți loga cu oricare dintre utilizatorii de mai jos, toți cu parola **`demo1234`**:

| Utilizator | Rol | Ce poate face |
|---|---|---|
| `admin` | Admin | gestionează clienții și semnăturile |
| `analyst1`, `analyst2` | Security Analyst | preia și închide detecții |
| `support` | Read-only | vede tot, dar nu poate modifica nimic |

Documentația interactivă a API-ului, generată de FastAPI, e la **http://localhost:8000/docs**.

<details>
<summary><b>Dacă preferați să nu rulați aplicația în Docker</b></summary>

Aveți nevoie de Python 3.12+ și de un Postgres:
- unul local;
- unul în cloud;
- sau doar baza de date din Docker, cu `docker compose up -d db`.

Dacă nu folosiți Postgres-ul din Docker, copiați `.env.example` în `.env` și setați `DATABASE_URL`. Apoi rulați scriptul de pornire. Acesta creează un `.venv`, instalează dependențele și pornește serverul:

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1   # Windows
```

```bash
./start.sh                                              # Linux / macOS
```

Schema se creează automat la pornire. Variabilele de mediu disponibile:

| Variabilă | Implicit | Rol |
|---|---|---|
| `DATABASE_URL` | `postgresql://postgres:postgres@localhost:5432/detections` | conexiunea la Postgres |
| `INGEST_API_KEY` | `dev-ingest-key` | cheia cerută de `POST /api/ingest` |
| `ENV` | — | `production` activează cookie-uri `Secure` (doar HTTPS) |

Valorile implicite sunt gândite doar pentru rulare locală.
</details>

---

## 2. Ce vă recomand să încercați (~10 minute)

**Un mic truc pentru a fi logați cu doi utilizatori în același browser:** deschideți un tab pe `http://localhost:8000` și altul pe `http://127.0.0.1:8000`. Browserul păstrează cookie-urile separat pentru cele două adrese, deci fiecare tab are sesiunea lui. Merge la fel de bine o fereastră incognito.

1. **Coada.** Logați-vă ca `analyst1`. Pagina principală e coada de detecții deschise, ordonată după prioritate (1–25). Detecțiile clientului „Alpha Bank” (importanță 5) sunt sus.
2. **Incidente noi, live.** Într-un terminal rulați:

   ```bash
   python -m scripts.simulate
   ```

   Scriptul trimite un incident aleator la fiecare 3 secunde. Coada se actualizează singură. Ca să trimiteți manual un incident:

   ```bash
   curl -X POST http://localhost:8000/api/ingest -H "Content-Type: application/json" -H "X-API-Key: dev-ingest-key" -d '{"customer_id": 1, "process": {"name": "powershell.exe", "encoded_command": true}}'
   ```

3. **Race condition-ul.** Cu `analyst1` într-un tab și `analyst2` în celălalt, apăsați **Claim** pe aceeași detecție în ambele. Unul o primește, iar celălalt vede mesajul „Too late: this detection was already claimed by analyst1.” Ca dovadă că nu e noroc la timing, rulați:

   ```bash
   python -m scripts.race
   ```

   Scriptul trimite 10 cereri de preluare simultane pentru aceeași detecție și arată că exact una reușește.

4. **O singură detecție activă.** Detecția preluată apare într-un panel fix în dreapta, vizibil pe orice pagină și după refresh. Dacă încercați să preluați încă una, cererea e refuzată.
5. **Închiderea.** Scrieți o rezoluție în panel și închideți detecția. Ea dispare din coadă, dar rămâne în pagina **Detections**, unde puteți filtra după status, client, semnătură și prioritate.
6. **Incidente fără potrivire.** Pagina **Unmatched** arată incidentele pentru care nu s-a găsit nicio semnătură sau niciun client cunoscut. Dacă adăugați apoi semnătura sau clientul care lipsea, incidentele respective devin detecții și dispar din listă.
7. **Roluri, verificate în API.** Ca `support` nu vedeți butoane de acțiune. Mai important e că serverul refuză și cererile directe: un `POST /api/detections/1/claim` fără sesiune primește `401`, iar cu sesiunea lui `support` primește `403`.
8. **Administrare.** Ca `admin`, schimbați importanța unui client direct din listă sau adăugați o semnătură nouă (de exemplu `process.name=nc.exe`). Incidentele trimise după aceea o folosesc imediat, iar incidentele unmatched primite înainte sunt reverificate.

Ca să reveniți oricând la datele inițiale:

```bash
python -m scripts.reset_db
```

Pentru comenzile `python -m scripts...` aveți nevoie de dependențe instalate local, prin `pip install -r requirements.txt` sau `.venv`-ul creat de `start.ps1`.

---

## 3. Unde să vă uitați în cod

Am încercat să păstrez codul mic și ușor de urmărit. Fiecare cerinta are un loc clar:

| Criteriu | Fișier | Ce găsiți acolo |
|---|---|---|
| Autentificare și autorizare | `app/auth.py`, `app/main.py` | sesiuni, parole, și rolul cerut de fiecare rută |
| Matching-ul semnăturilor | `app/matching.py` | funcții pure, fără bază de date |
| Calculul priorității | `app/priority.py` | o singură funcție |
| Fluxul de ingestie | `app/ingest.py` | client → semnături → prioritate → detecție |
| Race condition | `app/detections.py` | `claim_detection` și indexul din `app/schema.sql` |
| Coadă vs. pagina Detecții | `app/detections.py` | `get_queue` și `list_detections` |
| Teste | `tests/test_rules.py`, `tests/test_api.py` | unitare + integrare pe un server și un Postgres reale |

Restul fișierelor:
- `app/customers.py`, `app/signatures.py`: CRUD simplu.
- `app/db.py`: pool-ul de conexiuni.
- `app/seed.py`, `app/demo_data.py`: datele demo.
- `public/`: UI-ul.
- `scripts/`: scripturile de demo de mai sus.

### Testele

```bash
docker compose up -d db
```

```bash
pip install -r requirements-dev.txt
```

```bash
pytest -v
```

Testele de integrare pornesc un server real și folosesc o bază separată, `detections_test`. Datele demo ale aplicației nu sunt atinse. Același set rulează în GitHub Actions (`.github/workflows/ci.yml`), pe un Postgres real.

---

## 4. Deciziile mele și de ce

### Race condition-ul: rezolvat de baza de date, nu de aplicație
Preluarea unei detecții este un singur `UPDATE` condiționat:

```sql
UPDATE detections SET status = 'IN_PROGRESS', assigned_to = %s
WHERE id = %s AND status = 'OPEN'
```

Postgres blochează rândul pe durata actualizării. Când doi analiști preiau simultan aceeași detecție, al doilea `UPDATE` așteaptă, re-verifică `status = 'OPEN'` după ce primul s-a terminat, găsește condiția falsă și nu modifică nimic. Aplicația vede că nu s-a modificat niciun rând și răspunde cu **409**, spunând cine a preluat detecția.

Regula „un analist lucrează o singură detecție la un moment dat” e garantată tot în baza de date, printr-un index unic parțial:

```sql
CREATE UNIQUE INDEX one_active_detection_per_analyst ON detections (assigned_to) WHERE status = 'IN_PROGRESS';
```

Am evitat celelalte variante dintr-un motiv simplu:
- Un lock în memoria aplicației nu funcționează cu mai multe instanțe.
- Un „citește, verifică, apoi scrie” în Python are exact fereastra de race pe care vrem s-o eliminăm.
- `SELECT … FOR UPDATE` ar fi fost corect, dar face același lucru în doi pași.

Închiderea folosește același tipar: se închide doar detecția proprie, aflată în lucru, iar rezoluția e obligatorie.

### Autentificarea: sesiuni pe server, verificate la fiecare request
- Parolele sunt salvate ca hash `scrypt` cu salt, din biblioteca standard Python.
- După login, serverul creează o sesiune în baza de date și o trimite într-un cookie `httpOnly`, `SameSite=Lax`.
- Am ales sesiuni în locul JWT pentru că permit revocare imediată (logout, schimbare de rol) și nu au nevoie de refresh tokens. Pentru o singură aplicație pe un singur domeniu, JWT ar fi adăugat complexitate fără beneficiu.
- **Fiecare rută din API își declară rolul necesar** (`require_role(...)` în `app/main.py`). UI-ul doar ascunde butoanele. Testele verifică `401`/`403` pentru fiecare combinație relevantă de rol și acțiune.

| Acțiune | Admin | Analyst | Read-only |
|---|---|---|---|
| Vizualizare (coadă, detecții, clienți, semnături, unmatched) | ✅ | ✅ | ✅ |
| Gestionare clienți și semnături | ✅ | ❌ | ❌ |
| Preluare / închidere detecție | ❌ | ✅ | ❌ |

Brief-ul spune că „doar Security Analyștii pot să-și asigneze o detecție”, așa că Adminul nu poate prelua detecții, deși altfel are acces complet. Am preferat citirea literală, dar e o decizie ușor de schimbat.

Sursele externe trimit incidente la `POST /api/ingest` cu un **API key** în header-ul `X-API-Key`. Sunt sisteme, nu oameni, deci nu au sesiune de utilizator.

### Matching-ul semnăturilor
- O semnătură are una sau mai multe condiții `câmp = valoare` și se potrivește doar dacă **toate** sunt îndeplinite.
- Câmpurile pot fi imbricate și se adresează cu punct, de exemplu `process.name`.
- Valorile se compară ca text, așa cum apar în JSON, cu diferență între litere mari și mici: `3389` se potrivește cu `"3389"`, iar `true` cu `"true"`. Obiectele, listele și `null` nu se potrivesc niciodată.
- **Când se potrivesc mai multe semnături,** creez **o singură detecție**, pentru cea mai bună. Ordinea e: prioritatea cea mai mare, apoi cea mai specifică (mai multe condiții), apoi id-ul cel mai mic, ca rezultatul să fie mereu același. Toate semnăturile potrivite rămân salvate pe detecție (`matched_signature_ids`). Am ales asta ca să nu umplu coada cu duplicate pentru același incident.
- **Când nu se potrivește nimic sau clientul e necunoscut,** incidentul nu e ignorat. Îl salvez în `unmatched_incidents`, cu motivul, pentru audit și pentru reprocesare. Se vede în pagina **Unmatched**.
- **Reprocesarea incidentelor unmatched.** Când se creează sau se editează o semnătură, ori se adaugă un client, toate incidentele unmatched sunt verificate din nou cu semnăturile și clienții actuali. Cele care acum se potrivesc devin detecții și sunt scoase din `unmatched_incidents`, într-o singură tranzacție. Detecția primește ca dată de creare momentul în care a fost primit incidentul, deci își ocupă locul corect în coadă. Cele care tot nu se potrivesc rămân, cu motivul actualizat (de exemplu, clientul acum există, dar nu se potrivește nicio semnătură). `FOR UPDATE SKIP LOCKED` face ca două reprocesări simultane să nu transforme același incident în două detecții. Răspunsul API-ului conține câmpul `reprocessed`, cu numărul de detecții create, pe care UI-ul îl afișează.
  - Limită cunoscută: un incident primit exact în timp ce se salvează semnătura (a citit semnăturile înainte de salvare, dar a fost scris după reprocesare) rămâne unmatched până la următoarea reprocesare. Fereastra e de ordinul milisecundelor.

### Prioritatea
- `prioritate = importanța clientului (1–5) × prioritatea semnăturii (1–5)`, deci un scor între 1 și 25.
- Am ales produsul în locul sumei pentru că face combinația „client critic + semnătură critică” (25) să iasă clar în față, în timp ce un factor egal cu 1 ține detecția jos.
- Prioritatea se calculează **o singură dată, la crearea detecției**, și se salvează împreună cu componentele ei. Dacă se schimbă ulterior importanța unui client, coada nu se reordonează pe neașteptate, iar fiecare prioritate rămâne explicabilă (panelul activ arată calculul).
- În coadă, detecțiile cu aceeași prioritate sunt ordonate de la cea mai veche la cea mai nouă.

### Coada și pagina Detecții sunt separate intenționat
- **Coada** (`/api/queue`) arată doar ce necesită atenție: detecțiile deschise, ordonate după urgență. Se actualizează automat la 5 secunde.
- **Detections** (`/api/detections`) arată tot istoricul (deschise, în lucru, închise), cele mai noi primele, cu filtre.

### SQL scris direct, fără ORM
Interogările sunt puține și simple. Cu SQL explicit se vede exact ce garantează baza de date, lucru important mai ales la race condition, unde detaliile contează.

---

## Ce nu am implementat (și de ce)

Am preferat să livrez cerințele complet și testat, în loc să adaug funcționalități pe jumătate. Lucrurile pe care le-aș face în continuare:

- **Gestionarea utilizatorilor din UI.** Acum utilizatorii vin din datele demo.
- **Eliberarea unei detecții fără închidere și reasignarea de către admin.**
- **Un audit log complet.** Acum detecția păstrează cine a preluat-o, când și rezoluția, dar nu tot istoricul de evenimente.
- **Matching la scară mare.** Acum încarc toate semnăturile la fiecare incident, suficient pentru sute sau mii. Pentru volume mari aș folosi un index (câmp, valoare) → semnături sau un cache. Suport doar egalitate exactă: fără regex, intervale sau liste.
- **Rate limiting la login** și curățarea sesiunilor expirate (acum sunt doar ignorate).
- **Actualizări push** (SSE/WebSocket) în locul polling-ului la 5 secunde.
- **SSO (OIDC)** în locul login-ului cu parolă, pentru un mediu de producție.

Am mai luat două decizii conștiente:
- ștergerea unui client sau a unei semnături care au deja detecții e refuzată (`409`), ca să se păstreze istoricul;
- endpoint-urile sunt sincrone (FastAPI le rulează într-un thread pool), suficient pentru acest volum și mai simplu de urmărit.

### Hosting
Aplicația e un singur container, cu API și UI pe același domeniu, deci cookie-ul de sesiune funcționează fără CORS. Ar rula fără modificări, de exemplu:
- pe AWS App Runner sau ECS Fargate, cu RDS Postgres;
- gratuit, pe Render cu Postgres pe Neon.

Se setează doar `DATABASE_URL`, `INGEST_API_KEY` și `ENV=production`.



