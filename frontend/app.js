'use strict';

const views = {
  followups: 'پیگیری‌ها',
  overview: 'نمای کلی',
  inbox: 'صندوق مکالمات',
  listings: 'فایل‌ها و تطبیق',
  team: 'عملکرد مشاوران',
  reports: 'گزارش پایلوت',
};

const state = { tenant: '', key: '', token: '', data: null };

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
    headers: { 'Content-Type': 'application/json', ...(state.token ? { 'X-Session-Token': state.token } : { 'X-API-Key': state.key }) },
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
  $('#office-name').textContent = data.tenant.name;
  $('#connection-panel').hidden = true;
  $('#workspace').hidden = false;
  $('#refresh').disabled = false;
  $('#disconnect').hidden = false;
  const viewer = data.viewer;
  const isManager = !viewer || viewer.role === 'manager';
  $('#viewer-badge').textContent = isManager
    ? 'نمای مدیر: همه مشتریان و فایل‌های دفتر'
    : `نمای مشاور: ${viewer.name} — فقط مشتریان خودتان`;
  document.querySelectorAll('.nav-item[data-view="team"]').forEach((item) => { item.hidden = !isManager; });
  document.querySelectorAll('#listing-form, #agent-form-wrap, #channel-panel').forEach((node) => { node.hidden = !isManager; });
  if (!isManager && !views[currentView()]) showView('followups');
  setStatus('دفتر متصل است. اطلاعات این صفحه از سرور خوانده شده است.');
  render();
}

function empty(message) {
  const node = element('p', 'empty', message);
  return node;
}

function render() {
  renderFollowups();
  renderStats();
  renderRisks();
  renderLeads();
  renderListings();
  renderStale();
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

const BUCKETS = {
  critical: ['بیش از سه روز', 'critical'],
  overdue: ['بیش از ۲۴ ساعت', 'overdue'],
  unassigned: ['بدون مشاور', ''],
  waiting: ['در انتظار', ''],
};

function renderFollowups() {
  const container = $('#followup-list');
  container.replaceChildren();
  const followups = state.data.followups;
  if (!followups.length) return container.append(empty('مشتری‌ای منتظر پاسخ نیست.'));
  for (const item of followups) {
    const [label, tone] = BUCKETS[item.bucket];
    const row = element('button', 'lead-row lead-button');
    row.type = 'button';
    row.append(element('strong', '', text(item.lead.name || item.lead.contact)));
    row.append(element('span', `tag ${tone}`.trim(), label));
    row.append(element('span', 'tag', `${number(item.waiting_hours, ' ساعت')} انتظار`));
    row.append(element('span', 'tag', item.match_count ? `${number(item.match_count)} فایل قابل‌پیشنهاد` : 'بدون فایل مناسب'));
    row.addEventListener('click', () => {
      const lead = state.data.leads.find((candidate) => candidate.id === item.lead.id);
      if (!lead) return setStatus('این مشتری در نمای فعلی شما نیست.', true);
      showView('inbox');
      renderDetail(lead);
    });
    container.append(row);
  }
}

function currentView() {
  return document.querySelector('.nav-item[data-view].active')?.dataset.view;
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
  if (state.data.viewer && state.data.viewer.role !== 'manager') form.hidden = true;
  detail.append(form);

  const matches = element('div', 'matches');
  matches.append(element('h3', '', 'فایل‌های قابل‌پیشنهاد'));
  const matchList = element('div', '', '');
  matchList.append(empty('در حال خواندن تطبیق‌ها…'));
  matches.append(matchList);
  detail.append(matches);
  loadMatches(lead, matchList);
}

async function loadMatches(lead, container) {
  container.replaceChildren();
  try {
    const { matches } = await api('GET', `/v1/tenants/${encodeURIComponent(state.tenant)}/leads/${encodeURIComponent(lead.id)}/matches`);
    if (!matches.length) {
      container.append(empty(lead.intent.purpose === 'sell'
        ? 'این مشتری فروشنده است؛ تطبیق فایل برای خریدار و اجاره‌نشین انجام می‌شود.'
        : 'فایل متناسبی با نیاز و بودجهٔ این مشتری ثبت نشده است.'));
      return;
    }
    for (const match of matches) {
      const listing = match.listing;
      const row = element('div', 'lead-row');
      row.append(element('strong', '', listing.title));
      row.append(element('span', 'tag', listing.neighborhood));
      row.append(element('span', 'tag', listingLabel(listing)));
      row.append(element('span', 'tag', `${number(listing.bedrooms)} خواب`));
      row.append(element('span', 'tag', match.score ? `امتیاز ${number(match.score)}` : 'بدون امتیاز محله'));
      container.append(row);
    }
  } catch (error) {
    container.append(empty(`تطبیق‌ها خوانده نشد: ${error.message}`));
  }
}

function renderListings() {
  const container = $('#listing-list');
  container.replaceChildren();
  renderNeighborhoods();
  const listings = state.data.listings;
  if (!listings.length) return container.append(empty('فایلی ثبت نشده است.'));
  for (const listing of listings) container.append(listingRow(listing));
}

function listingRow(listing) {
  const row = element('div', 'lead-row');
  row.append(element('strong', '', listing.title));
  row.append(element('span', 'tag', listing.neighborhood));
  row.append(element('span', 'tag', listing.deal_type === 'rent' ? 'رهن و اجاره' : 'فروش'));
  row.append(element('span', 'tag', listingLabel(listing)));
  row.append(element('span', 'tag', listing.bedrooms ? `${number(listing.bedrooms)} خواب` : 'بدون خواب'));
  if (listing.updated_at) {
    row.append(element('span', 'tag', `آخرین به‌روزرسانی: ${new Intl.DateTimeFormat('fa-IR', { dateStyle: 'medium' }).format(new Date(listing.updated_at))}`));
  }
  const edit = element('button', 'outline-button', 'ویرایش');
  edit.type = 'button';
  edit.addEventListener('click', () => openListingEditor(listing));
  const remove = element('button', 'outline-button', 'حذف');
  remove.type = 'button';
  remove.addEventListener('click', () => deleteListing(listing, remove));
  row.append(edit, remove);
  return row;
}

function openListingEditor(listing) {
  const form = $('#listing-form');
  form.elements.title.value = listing.title;
  form.elements.neighborhood.value = listing.neighborhood;
  form.elements.bedrooms.value = String(Math.min(listing.bedrooms, 5));
  form.elements.deal_type.value = listing.deal_type;
  showDealFields(listing.deal_type);
  form.elements.price.value = listing.price ?? '';
  form.elements.deposit.value = listing.deposit ?? '';
  form.elements.rent.value = listing.rent ?? '';
  form.dataset.editing = listing.id;
  form.querySelector('button[type=submit]').textContent = 'ذخیره تغییرات';
  form.scrollIntoView({ block: 'start' });
  setStatus(`ویرایش فایل «${listing.title}»؛ برای انصراف فرم را خالی کنید.`);
}

function resetListingForm(form) {
  form.reset();
  delete form.dataset.editing;
  form.querySelector('button[type=submit]').textContent = 'ثبت فایل';
  showDealFields('sale');
}

async function deleteListing(listing, button) {
  if (!window.confirm(`فایل «${listing.title}» حذف شود؟ این کار برگشت‌پذیر نیست.`)) return;
  button.disabled = true;
  try {
    await api('DELETE', `/v1/tenants/${encodeURIComponent(state.tenant)}/listings/${encodeURIComponent(listing.id)}`);
    await loadWorkspace();
    setStatus('فایل حذف شد.');
  } catch (error) {
    setStatus(`فایل حذف نشد: ${error.message}`, true);
  } finally {
    button.disabled = false;
  }
}

async function renderStale() {
  const container = $('#stale-list');
  container.replaceChildren();
  try {
    const { stale } = await api('GET', `/v1/tenants/${encodeURIComponent(state.tenant)}/stale-listings`);
    if (!stale.length) return container.append(empty('فایل قدیمی‌ای نیست.'));
    for (const item of stale) {
      const row = listingRow(item.listing);
      row.prepend(element('span', 'tag overdue', `${number(item.age_days)} روز بدون به‌روزرسانی`));
      container.append(row);
    }
  } catch (error) {
    container.append(empty(`فهرست فایل‌های قدیمی خوانده نشد: ${error.message}`));
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
  for (const agent of agents) {
    const row = element('p', 'agent-row');
    row.append(document.createTextNode(agent.name));
    row.append(element('span', 'tag', agent.role === 'manager' ? 'مدیر' : 'مشاور'));
    container.append(row);
  }
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

const fields = (form) => Object.fromEntries(new FormData(form));

function fillOfficeId(tenant) {
  for (const form of document.querySelectorAll('#connection-form, #manager-form')) form.elements.tenant.value = tenant;
}

$('#connection-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const data = fields(form);
  const tenant = String(data.tenant).trim();
  setStatus('در حال ورود…');
  try {
    const password = String(data.password || '');
    const session = await api('POST', '/v1/sessions', { tenant, name: String(data.name).trim(), ...(password ? { password } : {}) });
    state.tenant = tenant;
    state.token = session.token;
    fillOfficeId(tenant);
    form.elements.name.value = '';
    form.elements.password.value = '';
    await loadWorkspace();
  } catch (error) {
    setStatus(`ورود انجام نشد: ${error.message}`, true);
  }
});

$('#manager-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const data = fields(form);
  state.tenant = String(data.tenant).trim();
  state.token = '';
  state.key = String(data.key).trim();
  fillOfficeId(state.tenant);
  setStatus('در حال اتصال…');
  try {
    await loadWorkspace();
  } catch (error) {
    state.key = '';
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
  const data = fields(form);
  const name = String(data.name).trim();
  const role = data.role;
  const password = String(data.password || '');
  try {
    await api('POST', `/v1/tenants/${encodeURIComponent(state.tenant)}/agents`, { name, role, ...(password ? { password } : {}) });
    await loadWorkspace();
    form.reset();
    setStatus(role === 'manager' ? 'مدیر افزوده شد.' : 'مشاور افزوده شد.');
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
  const editing = form.dataset.editing;
  try {
    if (editing) {
      await api('PATCH', `/v1/tenants/${encodeURIComponent(state.tenant)}/listings/${encodeURIComponent(editing)}`, payload);
    } else {
      await api('POST', `/v1/tenants/${encodeURIComponent(state.tenant)}/listings`, payload);
    }
    await loadWorkspace();
    resetListingForm(form);
    setStatus(editing ? 'تغییرات فایل ذخیره شد.' : 'فایل در دفتر ثبت شد.');
  } catch (error) {
    setStatus(`فایل ثبت نشد: ${error.message}`, true);
  } finally {
    submit.disabled = false;
  }
});

$('#channel-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const channel = new FormData(form).get('channel');
  const result = $('#channel-result');
  result.replaceChildren();
  try {
    const response = await api('POST', `/v1/tenants/${encodeURIComponent(state.tenant)}/channels/${encodeURIComponent(channel)}`);
    const url = `${location.origin}/v1/channels/${encodeURIComponent(state.tenant)}/${encodeURIComponent(channel)}`;
    result.append(element('p', '', `آدرس webhook: ${url}`));
    result.append(element('p', '', `سرصفحهٔ X-Channel-Secret: ${response.secret}`));
    result.append(element('p', 'empty', 'این کلید فقط همین یک بار نمایش داده می‌شود؛ آن را در تنظیمات کانال ذخیره کنید.'));
    setStatus('کلید کانال ساخته شد.');
  } catch (error) {
    setStatus(`کلید کانال ساخته نشد: ${error.message}`, true);
  }
});

$('#refresh').addEventListener('click', async () => {
  try {
    await loadWorkspace();
  } catch (error) {
    setStatus(`تازه‌سازی ناموفق: ${error.message}`, true);
  }
});

$('#disconnect').addEventListener('click', async () => {
  const tenant = state.tenant;
  if (state.token) {
    try {
      await api('DELETE', '/v1/sessions');
    } catch {
      // The local session is dropped either way; a stale token expires with the next request.
    }
  }
  state.tenant = '';
  state.key = '';
  state.token = '';
  state.data = null;
  fillOfficeId(tenant);
  $('#workspace').hidden = true;
  $('#lead-detail').hidden = true;
  $('#viewer-badge').textContent = '';
  $('#agent-form-wrap').hidden = false;
  $('#channel-panel').hidden = false;
  $('#channel-result').replaceChildren();
  resetListingForm($('#listing-form'));
  document.querySelectorAll('.nav-item[data-view="team"]').forEach((item) => { item.hidden = false; });
  $('#connection-panel').hidden = false;
  $('#refresh').disabled = true;
  $('#disconnect').hidden = true;
  $('#office-name').textContent = 'دفتر متصل نشده';
  setStatus('اتصال قطع شد.');
});

$('#today').textContent = new Intl.DateTimeFormat('fa-IR', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }).format(new Date());
