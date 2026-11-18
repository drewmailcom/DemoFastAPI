// Small single-page UI: hash routes (#/queue, #/detections, ...) rendered from the JSON API.
// The UI hides actions a role cannot perform, but the API is what actually enforces it.

const $ = (selector) => document.querySelector(selector);
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
const time = (iso) => (iso ? new Date(iso).toLocaleString() : '');
const IMPORTANCE = { 1: 'Low', 2: 'Moderate', 3: 'Medium', 4: 'High', 5: 'Critical' };

let me = null; // { user, active_detection }
let detectionFilters = {};
let signatures = [];

// ---- helpers ------------------------------------------------------------------------------

async function api(method, path, body) {
  const response = await fetch(`/api${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(errorMessage(data?.detail) ?? response.statusText);
  return data;
}

// FastAPI errors: a string, or a list of validation problems (422).
function errorMessage(detail) {
  if (!Array.isArray(detail)) return detail;
  return detail.map((problem) => `${problem.loc.at(-1)}: ${problem.msg}`).join('; ');
}

function flash(message, kind = 'error') {
  const el = $('#flash');
  el.textContent = message;
  el.className = kind;
  el.hidden = false;
  clearTimeout(flash.timer);
  flash.timer = setTimeout(() => (el.hidden = true), 6000);
}

/** Runs a user action, shows its error (e.g. "already claimed by analyst2"), then refreshes. */
async function act(action, successMessage) {
  try {
    const result = await action();
    if (successMessage) flash(withReprocessed(successMessage, result), 'ok');
  } catch (error) {
    flash(error.message);
  }
  await refresh();
}

// Saving a signature or adding a customer retries unmatched incidents; say how many became detections.
function withReprocessed(message, result) {
  const count = result?.reprocessed;
  if (!count) return message;
  return `${message}. ${count} unmatched incident${count === 1 ? '' : 's'} became detection${count === 1 ? '' : 's'}.`;
}

function onSubmit(selector, handler, successMessage) {
  $(selector).addEventListener('submit', (event) => {
    event.preventDefault();
    act(() => handler(Object.fromEntries(new FormData(event.target))), successMessage);
  });
}

function table(headers, rows) {
  if (rows.length === 0) return '<p class="empty">Nothing here.</p>';
  const head = headers.map((h) => `<th>${h}</th>`).join('');
  const body = rows.map((cells) => `<tr>${cells.map((c) => `<td>${c}</td>`).join('')}</tr>`).join('');
  return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

function select(name, options, selected) {
  const items = options.map(
    ([value, label]) =>
      `<option value="${esc(value)}" ${String(value) === String(selected ?? '') ? 'selected' : ''}>${esc(label)}</option>`,
  );
  return `<select name="${name}">${items.join('')}</select>`;
}

const priority = (p) => `<span class="badge ${p >= 15 ? 'high' : p >= 8 ? 'medium' : 'low'}">${p}</span>`;
const status = (s) => `<span class="status ${s}">${s.replace('_', ' ')}</span>`;
const button = (action, id, label, extra = '') =>
  `<button data-action="${action}" data-id="${id}" class="${extra}">${label}</button>`;
const isAdmin = () => me.user.role === 'ADMIN';
const isAnalyst = () => me.user.role === 'ANALYST';

// ---- pages --------------------------------------------------------------------------------

const pages = {
  async queue() {
    const rows = await api('GET', '/queue');
    $('#page').innerHTML =
      `<h1>Queue <small>${rows.length} open, most urgent first</small></h1>` +
      table(
        ['Priority', 'Received', 'Customer', 'Signature', ''],
        rows.map((d) => [
          priority(d.priority),
          time(d.created_at),
          esc(d.customer_name),
          esc(d.signature_name),
          isAnalyst() ? button('claim', d.id, 'Claim') : '',
        ]),
      );
  },

  async detections() {
    const query = new URLSearchParams(detectionFilters);
    const [rows, customers] = await Promise.all([api('GET', `/detections?${query}`), api('GET', '/customers')]);
    signatures = await api('GET', '/signatures');
    const f = detectionFilters;
    $('#page').innerHTML = `
      <h1>All detections <small>open, in progress and closed</small></h1>
      <form id="filters" class="row">
        ${select('status', [['', 'Any status'], ['OPEN', 'Open'], ['IN_PROGRESS', 'In progress'], ['CLOSED', 'Closed']], f.status)}
        ${select('customer_id', [['', 'Any customer'], ...customers.map((c) => [c.id, c.name])], f.customer_id)}
        ${select('signature_id', [['', 'Any signature'], ...signatures.map((s) => [s.id, s.name])], f.signature_id)}
        <input name="min_priority" type="number" min="1" max="25" placeholder="Min priority" value="${esc(f.min_priority)}">
        <button>Filter</button>
      </form>
      ${table(
        ['#', 'Priority', 'Received', 'Customer', 'Signature', 'Status', 'Analyst', 'Resolution'],
        rows.map((d) => [
          d.id,
          priority(d.priority),
          time(d.created_at),
          esc(d.customer_name),
          esc(d.signature_name),
          status(d.status),
          esc(d.assignee),
          esc(d.resolution),
        ]),
      )}`;
    $('#filters').addEventListener('submit', (event) => {
      event.preventDefault();
      // "Any ..." options and an empty priority box submit "", which the API rejects: leave them out.
      detectionFilters = Object.fromEntries([...new FormData(event.target)].filter(([, value]) => value !== ''));
      refresh();
    });
  },

  async unmatched() {
    const rows = await api('GET', '/unmatched');
    $('#page').innerHTML =
      '<h1>Unmatched incidents <small>no known customer or no matching signature</small></h1>' +
      table(
        ['Received', 'Reason', 'Payload'],
        rows.map((i) => [time(i.received_at), esc(i.reason), `<code>${esc(JSON.stringify(i.payload))}</code>`]),
      );
  },

  async customers() {
    const rows = await api('GET', '/customers');
    const importanceOptions = Object.entries(IMPORTANCE).map(([value, label]) => [value, `${value} - ${label}`]);
    $('#page').innerHTML =
      '<h1>Customers <small>importance feeds into detection priority</small></h1>' +
      table(
        ['Name', 'Importance', ''],
        rows.map((c) => [
          esc(c.name),
          isAdmin()
            ? `<span data-customer="${c.id}" data-name="${esc(c.name)}">${select('importance', importanceOptions, c.importance)}</span>`
            : `${c.importance} - ${IMPORTANCE[c.importance]}`,
          isAdmin() ? button('deleteCustomer', c.id, 'Delete', 'secondary') : '',
        ]),
      ) +
      (isAdmin()
        ? `<form id="customer-form" class="card row">
             <input name="name" placeholder="New customer name" required>
             ${select('importance', importanceOptions, 3)}
             <button>Add customer</button>
           </form>`
        : '');
    if (!isAdmin()) return;
    onSubmit('#customer-form', (form) => api('POST', '/customers', form), 'Customer added');
    // Changing the importance dropdown saves immediately.
    document.querySelectorAll('[data-customer] select').forEach((dropdown) =>
      dropdown.addEventListener('change', () => {
        const { customer, name } = dropdown.parentElement.dataset;
        act(() => api('PUT', `/customers/${customer}`, { name, importance: dropdown.value }), 'Importance saved');
      }),
    );
  },

  async signatures() {
    signatures = await api('GET', '/signatures');
    const conditionsText = (s) => s.conditions.map((c) => `${esc(c.field)} = ${esc(c.value)}`).join('<br>');
    $('#page').innerHTML =
      '<h1>Signatures <small>all conditions must match</small></h1>' +
      table(
        ['Name', 'Priority', 'Conditions', ''],
        signatures.map((s) => [
          esc(s.name),
          s.priority,
          `<code>${conditionsText(s)}</code>`,
          isAdmin() ? button('editSignature', s.id, 'Edit', 'secondary') + button('deleteSignature', s.id, 'Delete', 'secondary') : '',
        ]),
      ) +
      (isAdmin()
        ? `<form id="signature-form" class="card">
             <h2>New signature</h2>
             <input type="hidden" name="editId">
             <label>Name <input name="name" required></label>
             <label>Priority ${select('priority', [1, 2, 3, 4, 5].map((p) => [p, p]), 3)}</label>
             <label>Conditions, one <code>field=value</code> per line (dot-paths allowed, e.g. <code>process.name=cmd.exe</code>)
               <textarea name="conditions" rows="4" required></textarea></label>
             <button>Save signature</button>
           </form>`
        : '');
    if (!isAdmin()) return;
    onSubmit(
      '#signature-form',
      ({ editId, name, priority, conditions }) => {
        const body = {
          name,
          priority,
          conditions: conditions
            .split('\n')
            .filter((line) => line.trim())
            .map((line) => {
              const at = line.indexOf('=');
              return { field: line.slice(0, at).trim(), value: line.slice(at + 1).trim() };
            }),
        };
        return editId ? api('PUT', `/signatures/${editId}`, body) : api('POST', '/signatures', body);
      },
      'Signature saved',
    );
  },
};

// Buttons inside the page (rendered as HTML strings) are handled here by their data-action.
const actions = {
  claim: (id) => act(() => api('POST', `/detections/${id}/claim`), 'Detection claimed'),
  deleteCustomer: (id) => confirm('Delete this customer?') && act(() => api('DELETE', `/customers/${id}`), 'Customer deleted'),
  deleteSignature: (id) => confirm('Delete this signature?') && act(() => api('DELETE', `/signatures/${id}`), 'Signature deleted'),
  editSignature(id) {
    const s = signatures.find((sig) => sig.id === Number(id));
    const form = $('#signature-form');
    form.elements.editId.value = s.id;
    form.elements.name.value = s.name;
    form.elements.priority.value = s.priority;
    form.elements.conditions.value = s.conditions.map((c) => `${c.field}=${c.value}`).join('\n');
    form.querySelector('h2').textContent = `Edit signature #${s.id}`;
    form.scrollIntoView({ behavior: 'smooth' });
  },
};

$('#page').addEventListener('click', (event) => {
  const target = event.target.closest('button[data-action]');
  if (target) actions[target.dataset.action](target.dataset.id);
});

// ---- active detection panel ---------------------------------------------------------------

let panelDetectionId = null;

function renderActivePanel() {
  const d = me.active_detection;
  $('#active').hidden = !d;
  document.body.classList.toggle('has-active', Boolean(d));
  // Only rebuild when the detection changes, so a resolution being typed is not wiped by auto-refresh.
  if (!d || d.id === panelDetectionId) {
    if (!d) panelDetectionId = null;
    return;
  }
  panelDetectionId = d.id;
  $('#active').innerHTML = `
    <h2>Working on #${d.id} ${priority(d.priority)}</h2>
    <p><strong>${esc(d.signature_name)}</strong><br>${esc(d.customer_name)} · claimed ${time(d.assigned_at)}</p>
    <p class="muted">Priority ${d.priority} = customer importance ${d.customer_importance} × signature priority ${d.signature_priority}</p>
    <details open><summary>Incident</summary><pre>${esc(JSON.stringify(d.payload, null, 2))}</pre></details>
    <form id="close-form">
      <textarea name="resolution" rows="3" placeholder="Resolution (required)" required></textarea>
      <button>Close detection</button>
    </form>`;
  onSubmit('#close-form', (form) => api('POST', `/detections/${d.id}/close`, form), 'Detection closed');
}

// ---- login & routing ----------------------------------------------------------------------

function renderLogin() {
  $('#nav').hidden = true;
  $('#active').hidden = true;
  document.body.classList.remove('has-active');
  panelDetectionId = null;
  if ($('#login')) return; // already showing: keep what the user typed
  $('#page').innerHTML = `
    <form id="login" class="card narrow">
      <h1>Sign in</h1>
      <input name="username" placeholder="Username" required autofocus>
      <input name="password" type="password" placeholder="Password" required>
      <button>Sign in</button>
      <p class="muted">Demo users: admin, analyst1, analyst2, support. Password: <code>demo1234</code></p>
    </form>`;
  onSubmit('#login', async (form) => {
    await api('POST', '/auth/login', form);
    location.hash = '#/queue';
  });
}

async function refresh() {
  try {
    me = await api('GET', '/me');
  } catch {
    me = null; // logged out or session expired: stops the queue auto-refresh
    return renderLogin();
  }
  const route = location.hash.slice(2) || 'queue';
  $('#nav').hidden = false;
  $('#whoami').textContent = `${me.user.username} (${me.user.role})`;
  document.querySelectorAll('#nav a').forEach((a) => a.classList.toggle('current', a.hash === `#/${route}`));
  renderActivePanel();
  try {
    await (pages[route] ?? pages.queue)();
  } catch (error) {
    flash(error.message);
  }
}

$('#logout').addEventListener('click', () => act(() => api('POST', '/auth/logout')));
window.addEventListener('hashchange', refresh);
// The queue changes as incidents arrive: refresh it every 5 seconds.
setInterval(() => (location.hash || '#/queue') === '#/queue' && me && refresh(), 5000);
refresh();
