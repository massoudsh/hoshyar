'use strict';

const views = {
  overview: 'نمای کلی',
  inbox: 'صندوق مکالمات',
  listings: 'فایل‌ها و تطبیق',
  team: 'عملکرد مشاوران',
  reports: 'گزارش پایلوت',
};

const state = { tenant: '', key: '', data: null };

const $ = (selector) => document.querySelector(selector);
const statusBox = $('#status');

function text(value) {
  return value === null || value === undefined || value === '' ? '—' : String(value);
}

function element(tag, className, content) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content !== undefined) node.textContent = content;
  return node;
}

function setStatus(message, isError = false) {
  statusBox.textContent = message;
  statusBox.classList.toggle('error', isError);
}

function number(value, suffix = '') {
  return value === null || value === undefined ? '—' : `${new Intl.NumberFormat('fa-IR', { maximumFractionDigits: 1 }).format(value)}${suffix}`;
}

function percent(value) {
  return value === null || value === undefined ? '—' : `${number(value * 100)}٪`;
}

function amount(value) {
  return `${number(value)} تومان`;
}

function budgetLabel(intent) {
  if (intent.purpose === 'rent') {
    const deposit = intent.deposit ? `رهن تا ${amount(intent.deposit)}` : 'رهن نامشخص';
    const rent = intent.rent ? `اجاره تا ${amount(intent.rent)}` : 'اجاره نامشخص';
    return `${deposit} · ${rent}`;
  }
  return `بودجه: ${intent.price ? amount(intent.price) : 'نامشخص'}`;
}

function listingLabel(listing) {
  if (listing.deal_type === 'rent') {
    const parts = [];
    if (listing.deposit) parts.push(`رهن ${amount(listing.deposit)}`);
    if (listing.rent) parts.push(`اجاره ${amount(listing.rent)}`);
    return parts.length ? parts.join(' · ') : 'بدون مبلغ';
  }
  return listing.price ? amount(listing.price) : 'بدون مبلغ';
}

async function api(method, path, body) {
  const response = await fetch(path, {
    method,
    headers: { 'Content-Type': 'application/json', 'X-API-Key': state.key },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let payload = {};
  try {
    payload = await response.json();
  } catch {
    throw new Error(`پاسخ نامعتبر از سرور (${response.status})`);
  }
  if (!response.ok) throw new Error(payload.error || `درخواست ناموفق (${response.status})`);
  return payload;
}

async function loadWorkspace() {
  const data = await api('GET', `/v1/tenants/${encodeURIComponent(state.tenant)}/workspace`);
  state.data = data;
  localStorage.setItem('hoshyar.tenant', state.tenant);
  $('#office-name').textContent = data.tenant.name;
  $('#connection-panel').hidden = true;
  $('#workspace').hidden = false;
  $('#refresh').disabled = false;
  $('#disconnect').hidden = false;
  setStatus('دفتر متصل است. اطلاعات این صفحه از سرور خوانده شده است.');
  render();
}

function empty(message) {
  const node = element('p', 'empty', message);
  return node;
}

function render() {
  renderStats();
  renderRisks();
  renderLeads();
  renderListings();
  renderAgents();
  renderReport();
}

function renderStats() {
  const { dashboard, measurement, leads } = state.data;
  const container = $('#stats');
  container.replaceChildren();
  const cards = [
    ['مشتری فعال', number(dashboard.active_lead_count)],
    ['در انتظار پاسخ بیش از ۲۴ ساعت', number(dashboard.at_risk_leads.length)],
    ['بدون مشاور', number(dashboard.unassigned_leads.length)],
    ['میانگین زمان پاسخ', measurement.current.response_hours === null ? 'داده‌ای نیست' : number(measurement.current.response_hours, ' ساعت')],
    ['نرخ تبدیل', leads.length ? percent(measurement.current.conversion_rate) : 'داده‌ای نیست'],
  ];
  for (const [label, value] of cards) {
    const card = element('article', 'stat-card');
    card.append(element('p', '', label), element('strong', '', value));
    container.append(card);
  }
}

function renderRisks() {
  const container = $('#risk-list');
  container.replaceChildren();
  const risks = state.data.dashboard.at_risk_leads;
  if (!risks.length) return container.append(empty('هیچ مشتری در انتظاری بیش از ۲۴ ساعت نیست.'));
  for (const lead of risks) {
    const row = element('div', 'lead-row');
    row.append(element('strong', '', text(lead.name || lead.contact)));
    row.append(element('span', 'tag', `وضعیت: ${text(lead.state)}`));
    row.append(element('span', 'tag', lead.assigned_agent_id ? 'مشاور دارد' : 'بدون مشاور'));
    container.append(row);
  }
}

function filteredLeads() {
  const query = $('#lead-search').value.trim();
  return state.data.leads.filter((lead) =>
    !query || [lead.name, lead.contact, ...lead.messages.map((message) => message.body)]
      .some((value) => (value || '').includes(query)),
  );
}

function renderLeads() {
  const container = $('#lead-list');
  container.replaceChildren();
  const leads = filteredLeads();
  if (!leads.length) return container.append(empty('مشتری‌ای برای نمایش نیست.'));
  for (const lead of leads) {
    const button = element('button', 'lead-row lead-button');
    button.type = 'button';
    button.append(element('strong', '', text(lead.name || lead.contact)));
    button.append(element('span', 'tag', `${lead.messages.length} پیام`));
    button.append(element('span', 'tag', text(lead.intent.purpose)));
    button.addEventListener('click', () => renderDetail(lead));
    container.append(button);
  }
}

function renderDetail(lead) {
  const detail = $('#lead-detail');
  detail.hidden = false;
  detail.replaceChildren();
  const title = element('h2', '', text(lead.name || lead.contact));
  detail.append(title, element('p', '', `تماس: ${text(lead.contact)} · وضعیت: ${text(lead.state)}`));

  const intent = element('p', 'intent');
  intent.textContent = `نیاز: ${text(lead.intent.purpose)} · محله: ${text(lead.intent.neighborhood)} · ${budgetLabel(lead.intent)} · اطمینان قاعده‌محور: ${percent(lead.intent.confidence)}`;
  detail.append(intent);

  const messages = element('div', 'messages');
  for (const message of lead.messages) {
    messages.append(element('p', 'message', `[${text(message.channel)}] ${message.body}`));
  }
  detail.append(messages);

  const form = element('form', 'workspace-form');
  const select = element('select');
  select.name = 'agent_id';
  select.append(new Option('انتخاب مشاور', ''));
  for (const agent of state.data.agents) select.append(new Option(agent.name, agent.id));
  if (lead.assigned_agent_id) select.value = lead.assigned_agent_id;
  const label = element('label', '', 'تخصیص مشاور');
  label.append(select);
  const submit = element('button', 'primary-button', 'ذخیره تخصیص');
  submit.type = 'submit';
  form.append(label, submit);
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!select.value) return setStatus('ابتدا یک مشاور انتخاب کنید.', true);
    submit.disabled = true;
    try {
      await api('POST', `/v1/tenants/${encodeURIComponent(state.tenant)}/leads/${encodeURIComponent(lead.id)}/assignment`, { agent_id: select.value });
      await loadWorkspace();
      setStatus('تخصیص ذخیره شد.');
    } catch (error) {
      setStatus(`تخصیص ذخیره نشد: ${error.message}`, true);
    } finally {
      submit.disabled = false;
    }
  });
  detail.append(form);
}

function renderListings() {
  const container = $('#listing-list');
  container.replaceChildren();
  renderNeighborhoods();
  const listings = state.data.listings;
  if (!listings.length) return container.append(empty('فایلی ثبت نشده است.'));
  for (const listing of listings) {
    const row = element('div', 'lead-row');
    row.append(element('strong', '', listing.title));
    row.append(element('span', 'tag', listing.neighborhood));
    row.append(element('span', 'tag', listing.deal_type === 'rent' ? 'رهن و اجاره' : 'فروش'));
    row.append(element('span', 'tag', listingLabel(listing)));
    row.append(element('span', 'tag', listing.bedrooms ? `${number(listing.bedrooms)} خواب` : 'بدون خواب'));
    container.append(row);
  }
}

function renderNeighborhoods() {
  const names = new Set(state.data.listings.map((listing) => listing.neighborhood));
  $('#neighborhoods').replaceChildren(...[...names].map((name) => new Option(name, name)));
}

function showDealFields(dealType) {
  document.querySelectorAll('#listing-form [data-deal]').forEach((label) => {
    const active = label.dataset.deal === dealType;
    label.hidden = !active;
    if (!active) label.querySelector('input').value = '';
  });
}

// Accepts "750000000", "750,000,000" and "۷۵۰ میلیون"; an empty field returns null.
function parseAmount(raw) {
  const value = raw.trim().replace(/[\u0660-\u0669\u06f0-\u06f9]/g, (digit) => String(digit.charCodeAt(0) & 15));
  if (!value) return null;
  const match = value.replace(/[,٬\s]/g, '').match(/^(\d+(?:\.\d+)?)(میلیارد|میلیون|هزار)?$/);
  if (!match) throw new Error('مبلغ را فقط با رقم بنویسید، مثلاً ۷۵۰ میلیون');
  const unit = { 'میلیارد': 1e9, 'میلیون': 1e6, 'هزار': 1e3 }[match[2]] || 1;
  const amount = Math.round(Number(match[1]) * unit);
  if (!Number.isFinite(amount) || amount <= 0) throw new Error('مبلغ باید بزرگ‌تر از صفر باشد');
  return amount;
}

function renderAgents() {
  const container = $('#agent-list');
  container.replaceChildren();
  const agents = state.data.agents;
  if (!agents.length) return container.append(empty('مشاوری ثبت نشده است.'));
  for (const agent of agents) container.append(element('p', 'agent-row', agent.name));
}

function renderReport() {
  const container = $('#report');
  container.replaceChildren();
  const { baseline, current, change } = state.data.measurement;
  container.append(element('p', '', `میانگین زمان پاسخ کنونی: ${current.response_hours === null ? 'داده‌ای نیست' : number(current.response_hours, ' ساعت')}`));
  container.append(element('p', '', `خط پایه: ${baseline ? `${number(baseline.response_hours, ' ساعت')} · نرخ تبدیل ${percent(baseline.conversion_rate)}` : 'ثبت نشده'}`));
  container.append(element('p', '', change ? `تغییر زمان پاسخ: ${number(change.response_hours, ' ساعت')} · تغییر نرخ تبدیل: ${percent(change.conversion_rate)}` : 'برای مقایسه، خط پایه لازم است.'));
}

function showView(name) {
  if (!views[name]) return;
  document.querySelectorAll('.nav-item[data-view]').forEach((item) => item.classList.toggle('active', item.dataset.view === name));
  document.querySelectorAll('.workspace-view').forEach((view) => { view.hidden = view.id !== `${name}-view`; });
  $('#page-title').textContent = views[name];
}

document.querySelectorAll('.nav-item[data-view]').forEach((item) => item.addEventListener('click', () => showView(item.dataset.view)));

$('#connection-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const data = new FormData(event.currentTarget);
  state.tenant = String(data.get('tenant')).trim();
  state.key = String(data.get('key')).trim();
  setStatus('در حال اتصال…');
  try {
    await loadWorkspace();
  } catch (error) {
    setStatus(`اتصال برقرار نشد: ${error.message}`, true);
  }
});

$('#lead-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const data = new FormData(form);
  try {
    const payload = {
      name: String(data.get('name')).trim() || null,
      contact: String(data.get('contact')).trim(),
      channel: data.get('channel'),
      body: String(data.get('body')).trim(),
    };
    await api('POST', `/v1/tenants/${encodeURIComponent(state.tenant)}/messages`, payload);
    await loadWorkspace();
    form.reset();
    setStatus('پیام در دفتر ثبت شد.');
  } catch (error) {
    setStatus(`ثبت نشد: ${error.message}`, true);
  }
});

$('#agent-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const name = String(new FormData(form).get('name')).trim();
  try {
    await api('POST', `/v1/tenants/${encodeURIComponent(state.tenant)}/agents`, { name });
    await loadWorkspace();
    form.reset();
    setStatus('مشاور افزوده شد.');
  } catch (error) {
    setStatus(`مشاور افزوده نشد: ${error.message}`, true);
  }
});

$('#listing-form').elements.deal_type.addEventListener('change', (event) => showDealFields(event.currentTarget.value));

$('#listing-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const data = new FormData(form);
  const dealType = data.get('deal_type');
  const submit = form.querySelector('button[type=submit]');
  let payload;
  try {
    payload = {
      title: String(data.get('title')).trim(),
      neighborhood: String(data.get('neighborhood')).trim(),
      bedrooms: Number(data.get('bedrooms')),
      deal_type: dealType,
      price: dealType === 'sale' ? parseAmount(String(data.get('price') || '')) : null,
      deposit: dealType === 'rent' ? parseAmount(String(data.get('deposit') || '')) : null,
      rent: dealType === 'rent' ? parseAmount(String(data.get('rent') || '')) : null,
    };
    if (dealType === 'sale' && !payload.price) throw new Error('برای فایل فروش، قیمت کل لازم است');
    if (dealType === 'rent' && !payload.deposit && !payload.rent) throw new Error('رهن یا اجارهٔ ماهانه را وارد کنید');
  } catch (error) {
    return setStatus(`فایل ثبت نشد: ${error.message}`, true);
  }
  submit.disabled = true;
  try {
    await api('POST', `/v1/tenants/${encodeURIComponent(state.tenant)}/listings`, payload);
    await loadWorkspace();
    form.reset();
    showDealFields('sale');
    setStatus('فایل در دفتر ثبت شد.');
  } catch (error) {
    setStatus(`فایل ثبت نشد: ${error.message}`, true);
  } finally {
    submit.disabled = false;
  }
});

$('#refresh').addEventListener('click', async () => {
  try {
    await loadWorkspace();
  } catch (error) {
    setStatus(`تازه‌سازی ناموفق: ${error.message}`, true);
  }
});

$('#disconnect').addEventListener('click', () => {
  state.tenant = '';
  state.key = '';
  state.data = null;
  localStorage.removeItem('hoshyar.tenant');
  $('#workspace').hidden = true;
  $('#connection-panel').hidden = false;
  $('#refresh').disabled = true;
  $('#disconnect').hidden = true;
  $('#office-name').textContent = 'دفتر متصل نشده';
  setStatus('اتصال قطع شد.');
});

const savedTenant = localStorage.getItem('hoshyar.tenant');
if (savedTenant) $('#connection-form').elements.tenant.value = savedTenant;
$('#today').textContent = new Intl.DateTimeFormat('fa-IR', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }).format(new Date());
