# Detection Console

Platformă web simplificată pentru managementul detecțiilor de securitate. Incidentele primite prin HTTP sunt
corelate cu o bază de semnături, primesc o prioritate și intră într-o coadă din care analiștii le preiau și le rezolvă.

**Stack:** Python 3.12+ cu FastAPI, PostgreSQL 17 (prin `psycopg`, SQL scris direct, fără ORM), UI în HTML/JS simplu (fără build).

## Pornire

Ai două variante. Ambele pornesc aplicația la http://localhost:8000.

### Varianta 1: Docker (o singură comandă)

```bash
docker compose up --build
```

Pornește Postgres și aplicația. La prima pornire baza de date se populează automat cu date demo.

### Varianta 2: Python + un Postgres existent

1. Ai nevoie de un Postgres. Poate fi:
   - unul local;
   - unul gratuit în cloud (de exemplu Neon);
   - doar baza de date din Docker: `docker compose up -d db`.
2. Dacă nu folosești Postgres-ul din Docker, copiază `.env.example` în `.env` și setează `DATABASE_URL`.
3. Rulează scriptul de pornire. Acesta creează un `.venv`, instalează dependențele și pornește serverul:

```powershell
./start.ps1      # Windows
```

```bash
./start.sh       # Linux / macOS
```

Schema se creează automat la pornire, iar datele demo se încarcă dacă baza e goală.

### Utilizatori demo

| Utilizator | Rol | Parolă |
|---|---|---|
| `admin` | Admin | `demo1234` |
| `analyst1`, `analyst2` | Security Analyst | `demo1234` |
| `support` | Read-only | `demo1234` |

Documentația interactivă a API-ului (generată de FastAPI) e la http://localhost:8000/docs.

### Variabile de mediu

| Variabilă | Implicit | Rol |
|---|---|---|
| `DATABASE_URL` | `postgresql://postgres:postgres@localhost:5432/detections` | conexiunea la Postgres |
| `INGEST_API_KEY` | `dev-ingest-key` | cheia cerută de `POST /api/ingest` |
| `ENV` | — | `production` activează cookie-uri `Secure` (doar HTTPS) |

Valorile implicite sunt doar pentru dezvoltare. În producție se setează toate.

## Teste

```bash
docker compose up -d db                 # Postgres cu baza de test detections_test
pip install -r requirements-dev.txt
pytest -v
```

Testele de integrare pornesc un server real și lucrează pe baza `detections_test`, niciodată pe cea de dezvoltare. Altă bază se poate seta prin `TEST_DATABASE_URL`.

## Trimiterea unui incident

```bash
curl -X POST http://localhost:8000/api/ingest \
  -H "Content-Type: application/json" -H "X-API-Key: dev-ingest-key" \
  -d '{"customer_id": 1, "host": "bank-ws42", "process": {"name": "powershell.exe", "encoded_command": true}}'
```

Răspunsul este `201` cu detecția creată, sau `202` cu motivul pentru care incidentul a fost stocat ca unmatched.

## Structura codului

```
app/
  main.py          toate rutele HTTP și rolul cerut de fiecare (doar stratul HTTP)
  auth.py          parole (scrypt), sesiuni, dependențele current_user / require_role / require_ingest_key
  ingest.py        fluxul de ingestie: client → semnături → prioritate → detecție
  matching.py      matching-ul semnăturilor (funcții pure)
  priority.py      calculul priorității (funcție pură)
  detections.py    coada, lista de detecții, claim / close (race-safe)
  customers.py     CRUD clienți
  signatures.py    CRUD semnături
  validation.py    tipul Text folosit la validarea input-ului
  db.py            pool de conexiuni + helperi query / execute
  schema.sql       schema bazei de date (idempotentă, aplicată la fiecare pornire)
  seed.py, demo_data.py   date demo
public/            UI-ul (index.html, app.js, style.css), servit de aceeași aplicație
scripts/           reset DB, simulator de incidente, demo race condition
tests/             test_rules.py (unitare), test_api.py (integrare, server și Postgres reale)
```

## Decizii de arhitectură

### Autentificare și autorizare
- Login cu username și parolă. Parolele sunt salvate ca hash `scrypt` cu salt, din biblioteca standard Python.
- **Sesiuni pe server** (tabela `sessions`), transmise printr-un cookie `httpOnly`, `SameSite=Lax`. Am ales sesiuni în loc de JWT pentru că permit revocare imediată (logout, schimbare de rol) și nu au nevoie de refresh tokens. Pentru un singur serviciu și un singur domeniu, JWT ar fi adăugat complexitate fără beneficiu.
- **Autorizarea se face în API**, prin dependențe FastAPI pe fiecare rută (`require_role(...)` în `main.py`). UI-ul doar ascunde butoanele. Testele verifică `401`/`403` pentru fiecare rol.

| Acțiune | Admin | Analyst | Read-only |
|---|---|---|---|
| Vizualizare (coadă, detecții, clienți, semnături, unmatched) | ✅ | ✅ | ✅ |
| CRUD clienți și semnături | ✅ | ❌ | ❌ |
| Preluare / închidere detecție | ❌ | ✅ | ❌ |

> Brief-ul spune că „doar Security Analyștii pot să-și asigneze o detecție”, deci Adminul nu poate prelua detecții, chiar dacă altfel are acces complet.

- **Ingestia** (`POST /api/ingest`) folosește un API key în header-ul `X-API-Key`. Sursele externe sunt sisteme, nu utilizatori, deci nu au sesiune.
- **Validarea input-ului** se face cu modele Pydantic. Datele invalide primesc `422` cu detalii.

### Matching-ul semnăturilor (`app/matching.py`)
- O semnătură are una sau mai multe condiții `câmp = valoare`. Se potrivește doar dacă **toate** condițiile sunt îndeplinite (AND).
- Câmpurile pot fi imbricate și se adresează prin dot-path (de exemplu `process.name`).
- Valorile se compară ca text, așa cum apar în JSON, cu diferență între litere mari și mici: `3389` se potrivește cu `"3389"`, iar `true` cu `"true"`. Obiectele, array-urile și `null` nu se potrivesc niciodată.
- **Mai multe semnături potrivite:** se creează **o singură detecție**, pentru semnătura cea mai bună. Ordinea e: prioritatea cea mai mare, apoi cea mai specifică (cele mai multe condiții), apoi id-ul cel mai mic, ca rezultatul să fie determinist. Toate semnăturile potrivite sunt salvate în `matched_signature_ids`. Am ales asta ca să nu umplem coada cu duplicate pentru același incident.
- **Nicio semnătură potrivită sau client necunoscut:** incidentul se salvează în `unmatched_incidents`, cu motivul (`NO_SIGNATURE` / `UNKNOWN_CUSTOMER`), și e vizibil în pagina *Unmatched*. Nu le ignorăm, pentru audit și ca să le putem reprocesa când se adaugă o semnătură nouă. `customer_id` trebuie să fie un număr întreg.

### Prioritatea (`app/priority.py`)
- `prioritate = importanța clientului (1–5) × prioritatea semnăturii (1–5)`, deci între 1 și 25.
- Produsul face ca „client critic + semnătură critică” (25) să iasă mult în față, iar un factor egal cu 1 ține detecția jos.
- Prioritatea și cele două componente se salvează **la crearea detecției** (snapshot). Dacă se schimbă ulterior importanța unui client, detecțiile existente nu se reordonează, iar prioritatea fiecărei detecții poate fi explicată.
- Coada e ordonată după `priority DESC`, apoi `created_at ASC` (FIFO în cadrul aceleiași priorități).

### Race condition la preluare (`app/detections.py`)
Preluarea e un singur `UPDATE` condiționat:

```sql
UPDATE detections SET status = 'IN_PROGRESS', assigned_to = %s
WHERE id = %s AND status = 'OPEN'
```

Postgres blochează rândul. Când doi analiști preiau simultan aceeași detecție, al doilea `UPDATE` așteaptă, re-evaluează `status = 'OPEN'` după commit-ul primului, găsește condiția falsă și nu modifică nimic. Aplicația vede 0 rânduri modificate și răspunde **409** cu mesajul „already claimed by analyst1”.

Regula „un analist lucrează o singură detecție” este garantată tot de baza de date, printr-un **partial unique index**:

```sql
CREATE UNIQUE INDEX one_active_detection_per_analyst ON detections (assigned_to) WHERE status = 'IN_PROGRESS';
```

De ce nu alte variante:
- Un lock în memoria aplicației nu funcționează cu mai multe instanțe sau procese.
- Un „citește, verifică, apoi scrie” în Python (de exemplu `SELECT` urmat de `UPDATE`) are exact fereastra de race pe care vrem s-o evităm.
- `SELECT … FOR UPDATE` ar fi corect, dar face același lucru în doi pași.

Testele de integrare trimit 10 cereri simultane și verifică exact un `200` și nouă `409`. Același lucru se poate vedea live cu `python -m scripts.race`.

Închiderea folosește același model: `UPDATE … WHERE id = %s AND assigned_to = %s AND status = 'IN_PROGRESS'`. Rezoluția este obligatorie.

### Coada vs. pagina Detecții
- `GET /api/queue`: doar detecțiile `OPEN`, ordonate după urgență. Este pagina principală și se actualizează automat la 5 secunde.
- `GET /api/detections`: toate detecțiile (deschise, în lucru, închise), cele mai noi primele, cu filtre după status, client, semnătură și prioritate minimă.

### Detecția activă
Un panel fix în dreapta, vizibil pe orice pagină. Starea vine din server (`GET /api/me`), deci rămâne și după refresh sau re-login.

### Accesul la baza de date
Am folosit SQL scris direct (`psycopg` 3, cu pool de conexiuni) în loc de ORM. Interogările sunt puține și simple, iar SQL-ul explicit face ușor de văzut și de explicat exact ce garantează baza de date, mai ales pentru race condition.

## Demo

```bash
python -m scripts.simulate   # trimite un incident aleator la fiecare 3 s
python -m scripts.race       # 10 preluări simultane ale aceleiași detecții → exact un câștigător
python -m scripts.reset_db   # date demo curate
```

Scenariu sugerat:
1. Pornești simulatorul. Coada se umple, iar detecțiile clientului critic urcă sus.
2. Deschizi două ferestre (una normală, una incognito) cu `analyst1` și `analyst2` și preiei aceeași detecție din ambele. Unul o primește, celălalt vede cine a luat-o.
3. Încerci să preiei a doua detecție cu același analist: e refuzată.
4. Închizi detecția cu o rezoluție. Dispare din coadă și rămâne în *Detections*.
5. Ca `support`, nu ai butoane de acțiune. Un `curl` direct la `/api/detections/1/claim` primește `401`/`403`.
6. Ca `admin`, schimbi importanța unui client sau adaugi o semnătură, apoi trimiți un incident care o folosește.

## CI și hosting
- **GitHub Actions** (`.github/workflows/ci.yml`): testele pe un Postgres real (service container) și build-ul imaginii Docker.
- **Hosting:** aplicația e un singur container, cu API și UI pe același domeniu, deci cookie-ul de sesiune funcționează fără CORS.
  - Variantă gratuită: Render (Web Service din `Dockerfile`, cu deploy automat din GitHub) plus Postgres pe Neon.
  - Pe AWS: App Runner sau ECS Fargate, cu RDS Postgres.
  - Se setează `DATABASE_URL`, `INGEST_API_KEY` și `ENV=production`.

## Limitări cunoscute / ce nu am implementat
- **Gestionarea utilizatorilor** nu e în UI. Utilizatorii vin din seed (brief-ul nu o cere).
- **Nu există „release” al unei detecții** (renunțare fără închidere) și nici reasignare de către admin.
- **Fără audit log separat.** Detecția păstrează cine a preluat-o, când și rezoluția, dar nu un istoric complet de evenimente.
- **Matching-ul** încarcă toate semnăturile la fiecare incident. Este suficient pentru sute sau mii de semnături. La scară mare ar fi nevoie de un index (câmp, valoare) → semnături sau de cache. Doar egalitate exactă: fără regex, intervale sau array-uri.
- Incidentele unmatched nu sunt reprocesate automat când apare o semnătură nouă.
- **Fără rate limiting la login** și fără curățarea sesiunilor expirate (sunt doar ignorate).
- Coada se actualizează prin polling, nu prin push (SSE/WebSocket).
- Ștergerea unui client sau a unei semnături care are deja detecții e refuzată (`409`), pentru a păstra istoricul.
- Endpoint-urile sunt sincrone (FastAPI le rulează într-un thread pool). Pentru volumul acestei aplicații e suficient și mai simplu decât varianta async.

## Cum am folosit AI
<!-- De completat: ce ai delegat, ce ai verificat sau corectat tu, ce decizii ți-ai asumat. -->
