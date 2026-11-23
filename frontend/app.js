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
  renderReminders();
  renderStats();
  renderRisks();
  renderCold();
  renderLeads();
  renderListings();
  renderQueue();
  renderCompareOptions();
  renderSavedSearches();
  renderTrend();
  renderSuspicious();
  renderAgents();
  renderPerformance();
  renderReport();
  renderSourceHealth();
}

function renderReminders() {
  const container = $('#reminder-list');
  container.replaceChildren();
  const reminders = state.data.reminders || [];
  if (!reminders.length) return container.append(empty('بازدیدی برای ۲۴ ساعت آینده برنامه‌ریزی نشده است.'));
  for (const reminder of reminders) {
    const row = element('div', 'lead-row');
    row.append(element('strong', '', reminder.lead_name || 'مشتری'));
    row.append(element('span', 'tag', new Intl.DateTimeFormat('fa-IR', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(reminder.starts_at))));
    row.append(element('span', 'tag', reminder.agent_name ? `مشاور: ${reminder.agent_name}` : 'بدون مشاور'));
    row.append(element('span', 'tag', state.data.listings.find((item) => item.id === reminder.listing_id)?.title || 'فایل'));
    container.append(row);
  }
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
    ['فایل تازه‌نشده', number(dashboard.stale_listing_count)],
    ['بازدید پیش‌رو', number(dashboard.upcoming_viewings)],
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
    row.append(element('span', 'tag', item.owner_name ? `مسئول: ${item.owner_name}` : 'بدون مشاور'));
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

function renderCold() {
  const container = $('#cold-list');
  container.replaceChildren();
  const cold = state.data.dashboard.cold_leads || [];
  if (!cold.length) return container.append(empty('مشتری سردی نیست.'));
  for (const lead of cold) {
    const row = element('div', 'lead-row');
    row.append(element('strong', '', text(lead.name || lead.contact)));
    row.append(element('span', 'tag', `وضعیت: ${text(lead.state)}`));
    const button = element('button', 'outline-button', 'سرد کردن');
    button.type = 'button';
    button.addEventListener('click', async () => {
      button.disabled = true;
      try {
        await api('POST', `/v1/tenants/${encodeURIComponent(state.tenant)}/leads/${encodeURIComponent(lead.id)}/cold`);
        await loadWorkspace();
        setStatus('مشتری سرد شد.');
      } catch (error) {
        setStatus(`سرد کردن انجام نشد: ${error.message}`, true);
        button.disabled = false;
      }
    });
    row.append(button);
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

  const draftBox = element('section', 'draft-box');
  draftBox.append(element('h3', '', 'پیش‌نویس پاسخ'));
  const hint = element('p', 'empty', 'پیش‌نویس از همان چیزی ساخته می‌شود که مشتری گفته است؛ قبل از ارسال ویرایشش کنید.');
  const draftButton = element('button', 'outline-button', 'ساخت پیش‌نویس پاسخ');
  draftButton.type = 'button';
  draftBox.append(hint, draftButton);
  const textarea = element('textarea');
  textarea.rows = 4;
  textarea.hidden = true;
  const sendButton = element('button', 'primary-button', 'ثبت پاسخ در دفتر');
  sendButton.type = 'button';
  sendButton.hidden = true;
  draftButton.addEventListener('click', async () => {
    draftButton.disabled = true;
    try {
      const draft = await api('GET', `/v1/tenants/${encodeURIComponent(state.tenant)}/leads/${encodeURIComponent(lead.id)}/draft`);
      textarea.value = draft.text;
      textarea.hidden = false;
      sendButton.hidden = false;
      setStatus('پیش‌نویس آماده است؛ پیش از ثبت ویرایشش کنید.');
    } catch (error) {
      setStatus(`پیش‌نویس ساخته نشد: ${error.message}`, true);
    } finally {
      draftButton.disabled = false;
    }
  });
  sendButton.addEventListener('click', async () => {
    const body = textarea.value.trim();
    if (!body) return setStatus('متن پاسخ خالی است.', true);
    sendButton.disabled = true;
    try {
      const viewer = state.data.viewer;
      await api('POST', `/v1/tenants/${encodeURIComponent(state.tenant)}/messages`, {
        contact: lead.contact, body, channel: 'manual', direction: 'outbound',
        ...(viewer ? { agent_id: viewer.id } : {}),
      });
      await loadWorkspace();
      setStatus('پاسخ در دفتر ثبت شد و مشتری از صف پیگیری خارج شد.');
    } catch (error) {
      setStatus(`پاسخ ثبت نشد: ${error.message}`, true);
    } finally {
      sendButton.disabled = false;
    }
  });
  draftBox.append(textarea, sendButton);
  detail.append(draftBox);

  const visitForm = element('form', 'workspace-form');
  const visitSelect = element('select');
  visitSelect.name = 'listing_id';
  visitSelect.append(new Option('فایل مورد بازدید', ''));
  for (const listing of state.data.listings) visitSelect.append(new Option(`${listing.title} — ${listing.neighborhood}`, listing.id));
  const visitTime = element('input');
  visitTime.type = 'datetime-local';
  visitTime.name = 'starts_at';
  visitTime.required = true;
  const visitLabel = element('label', '', 'برنامهٔ بازدید');
  visitLabel.append(visitSelect);
  const timeLabel = element('label', '', 'زمان');
  timeLabel.append(visitTime);
  const visitSubmit = element('button', 'outline-button', 'ثبت بازدید');
  visitSubmit.type = 'submit';
  visitForm.append(visitLabel, timeLabel, visitSubmit);
  visitForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!visitSelect.value || !visitTime.value) return setStatus('فایل و زمان بازدید لازم است.', true);
    visitSubmit.disabled = true;
    try {
      await api('POST', `/v1/tenants/${encodeURIComponent(state.tenant)}/viewings`, {
        lead_id: lead.id, listing_id: visitSelect.value, starts_at: new Date(visitTime.value).toISOString(),
      });
      await loadWorkspace();
      setStatus('بازدید ثبت شد و در یادآوری‌های ۲۴ ساعت آینده دیده می‌شود.');
    } catch (error) {
      setStatus(`بازدید ثبت نشد: ${error.message}`, true);
    } finally {
      visitSubmit.disabled = false;
    }
  });
  detail.append(visitForm);
}

const REASONS = {
  'price close to the stated budget': 'قیمت نزدیک بودجه',
  'deposit within budget': 'رهن در محدودهٔ بودجه',
  'monthly rent within budget': 'اجاره در محدودهٔ بودجه',
};

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
      row.append(element('span', 'tag', `امتیاز ${number(match.score)}`));
      if (match.reasons && match.reasons.length) {
        row.append(element('span', 'tag', REASONS[match.reasons[0]] || match.reasons[0]));
      }
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
  if (listing.area) row.append(element('span', 'tag', `${number(listing.area)} متر`));
  if (listing.verified_at) row.append(element('span', 'tag verified', 'تأیید حضوری'));
  else row.append(element('span', 'tag unverified', 'تأییدنشده'));
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
  form.elements.area.value = listing.area ?? '';
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
  const select = $('#search-form').elements.lead_id;
  select.replaceChildren(new Option('بدون مشتری', ''));
  for (const lead of state.data.leads) select.append(new Option(lead.name || lead.contact, lead.id));
}

async function renderQueue() {
  const container = $('#review-queue');
  container.replaceChildren();
  try {
    const { queue } = await api('GET', `/v1/tenants/${encodeURIComponent(state.tenant)}/review-queue`);
    if (!queue.length) return container.append(empty('همهٔ فایل‌ها تازه و تأییدشده‌اند.'));
    for (const item of queue) {
      const row = listingRow(item.listing);
      row.prepend(element('span', 'tag overdue', `${number(item.age_days)} روز`));
      row.append(element('span', 'tag', item.needs.join(' · ')));
      const touch = element('button', 'outline-button', 'هنوز موجود است');
      touch.type = 'button';
      touch.addEventListener('click', () => listingAction(item.listing, 'touch', touch, 'تاریخ تازگی به‌روز شد.'));
      const verify = element('button', 'outline-button', 'تأیید حضوری');
      verify.type = 'button';
      verify.addEventListener('click', () => listingAction(item.listing, 'verify', verify, 'مهر تأیید حضوری ثبت شد.'));
      row.append(touch, verify);
      container.append(row);
    }
  } catch (error) {
    container.append(empty(`صف بازبینی خوانده نشد: ${error.message}`));
  }
}

async function listingAction(listing, action, button, message) {
  button.disabled = true;
  try {
    const viewer = state.data.viewer;
    await api('POST', `/v1/tenants/${encodeURIComponent(state.tenant)}/listings/${encodeURIComponent(listing.id)}/${action}`,
      action === 'verify' && !viewer ? { agent_id: state.data.agents[0]?.id } : undefined);
    await loadWorkspace();
    setStatus(message);
  } catch (error) {
    setStatus(`انجام نشد: ${error.message}`, true);
    button.disabled = false;
  }
}

function renderCompareOptions() {
  const select = $('#compare-form').elements.ids;
  select.replaceChildren(...state.data.listings.map((listing) =>
    new Option(`${listing.title} — ${listing.neighborhood} — ${listingLabel(listing)}`, listing.id)));
}

function renderSavedSearches() {
  const container = $('#saved-search-list');
  container.replaceChildren();
  const searches = state.data.saved_searches || [];
  if (!searches.length) return container.append(empty('جست‌وجوی ذخیره‌شده‌ای نیست.'));
  for (const search of searches) {
    const row = element('div', 'lead-row');
    row.append(element('strong', '', search.name));
    row.append(element('span', 'tag', search.deal_type === 'rent' ? 'رهن و اجاره' : 'فروش'));
    if (search.max_price) row.append(element('span', 'tag', `تا ${amount(search.max_price)}`));
    if (search.max_deposit) row.append(element('span', 'tag', `رهن تا ${amount(search.max_deposit)}`));
    if (search.max_rent) row.append(element('span', 'tag', `اجاره تا ${amount(search.max_rent)}`));
    if (search.neighborhood) row.append(element('span', 'tag', search.neighborhood));
    const button = element('button', 'outline-button', 'فایل‌های جور');
    button.type = 'button';
    button.addEventListener('click', async () => {
      button.disabled = true;
      try {
        const { matches } = await api('GET', `/v1/tenants/${encodeURIComponent(state.tenant)}/saved-searches/${encodeURIComponent(search.id)}/matches`);
        setStatus(matches.length ? `${number(matches.length)} فایل با این جست‌وجو جور است: ${matches.map((match) => match.listing.title).join('، ')}`
          : 'هیچ فایلی الان با این جست‌وجو جور نیست.');
      } catch (error) {
        setStatus(`جست‌وجو انجام نشد: ${error.message}`, true);
      } finally {
        button.disabled = false;
      }
    });
    row.append(button);
    container.append(row);
  }
}

async function loadTrend(neighborhood) {
  const container = $('#trend-result');
  container.replaceChildren(empty('در حال خواندن روند…'));
  try {
    const query = new URLSearchParams({ months: '6' });
    if (neighborhood) query.set('neighborhood', neighborhood);
    const trend = await api('GET', `/v1/tenants/${encodeURIComponent(state.tenant)}/market-trend?${query}`);
    container.replaceChildren();
    if (!trend.points.length) return container.append(empty('برای این محله قیمتی از فایل‌های فروش ثبت نشده است.'));
    for (const point of trend.points) {
      const row = element('div', 'lead-row');
      row.append(element('strong', '', point.month));
      row.append(element('span', 'tag', `میانگین ${amount(point.average)}`));
      row.append(element('span', 'tag', `${number(point.count)} فایل`));
      container.append(row);
    }
    container.append(element('p', '', trend.change_percent === null
      ? 'برای محاسبهٔ تغییر، دست‌کم دو ماه داده لازم است.'
      : `تغییر نسبت به ابتدای بازه: ${number(trend.change_percent)}٪`));
  } catch (error) {
    container.replaceChildren(empty(`روند خوانده نشد: ${error.message}`));
  }
}

function renderTrend() {
  if (!$('#trend-result').childElementCount) {
    $('#trend-result').append(element('p', 'empty', 'برای دیدن روند قیمت، دکمهٔ «نمایش روند» را بزنید.'));
  }
}

async function renderSuspicious() {
  const container = $('#suspicious-list');
  container.replaceChildren();
  try {
    const { suspicious } = await api('GET', `/v1/tenants/${encodeURIComponent(state.tenant)}/suspicious-listings`);
    if (!suspicious.length) return container.append(empty('قیمت مشکوکی پیدا نشد.'));
    for (const finding of suspicious) {
      const row = element('div', 'lead-row');
      row.append(element('strong', '', finding.listing.title));
      row.append(element('span', 'tag overdue', finding.reason === 'sale price below its own deposit'
        ? 'قیمت فروش از رهن کمتر است' : `حدود ${number(finding.discount_percent)}٪ زیر هم‌محله‌ای‌ها`));
      row.append(element('span', 'tag', listingLabel(finding.listing)));
      if (finding.market_average) row.append(element('span', 'tag', `میانگین محله: ${amount(finding.market_average)}`));
      container.append(row);
    }
  } catch (error) {
    container.append(empty(`بررسی قیمت انجام نشد: ${error.message}`));
  }
}

async function renderSourceHealth() {
  const container = $('#source-health');
  container.replaceChildren();
  try {
    const { channels } = await api('GET', `/v1/tenants/${encodeURIComponent(state.tenant)}/source-health`);
    if (!channels.length) return container.append(empty('هنوز پیامی از کانال‌ها نرسیده است.'));
    for (const row of channels) {
      const line = element('div', 'lead-row');
      line.append(element('strong', '', row.channel));
      line.append(element('span', 'tag', `${number(row.leads)} مشتری`));
      line.append(element('span', 'tag', `${percent(row.unanswered_rate)} بی‌پاسخ`));
      line.append(element('span', 'tag', `تبدیل ${percent(row.conversion_rate)}`));
      container.append(line);
    }
  } catch (error) {
    container.append(empty(`سلامت کانال‌ها خوانده نشد: ${error.message}`));
  }
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

function performanceQuery() {
  const days = $('#performance-form').elements.period.value;
  if (days === 'all') return '';
  const since = new Date(Date.now() - Number(days) * 86400000).toISOString();
  return `?since=${encodeURIComponent(since)}`;
}

async function renderPerformance() {
  const container = $('#performance-report');
  container.replaceChildren();
  container.append(empty('در حال خواندن گزارش…'));
  try {
    const report = await api('GET', `/v1/tenants/${encodeURIComponent(state.tenant)}/performance${performanceQuery()}`);
    container.replaceChildren();
    const office = report.office;
    container.append(element('p', '', office.replies
      ? `مجموع دفتر: ${number(office.response_hours, ' ساعت')} میانگین پاسخ در ${number(office.replies)} پاسخ`
      : 'در این بازه پاسخی ثبت نشده است.'));
    if (!report.agents.length) return container.append(empty('مشاوری ثبت نشده است.'));
    for (const row of report.agents) {
      const line = element('div', 'lead-row');
      line.append(element('strong', '', row.agent.name));
      line.append(element('span', 'tag', row.agent.role === 'manager' ? 'مدیر' : 'مشاور'));
      line.append(element('span', 'tag', row.response_hours === null ? 'بدون پاسخ در بازه' : `میانگین پاسخ ${number(row.response_hours, ' ساعت')}`));
      line.append(element('span', 'tag', `${number(row.replies)} پاسخ`));
      line.append(element('span', 'tag', `${number(row.lead_count)} مشتری`));
      line.append(element('span', 'tag', `${number(row.unanswered_count)} بی‌پاسخ`));
      line.append(element('span', 'tag', `تبدیل ${percent(row.conversion_rate)}`));
      container.append(line);
    }
  } catch (error) {
    container.replaceChildren(empty(`گزارش خوانده نشد: ${error.message}`));
  }
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
      area: data.get('area') ? Number(String(data.get('area')).replace(/[^\d.]/g, '')) : null,
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
      const { alerts } = await api('POST', `/v1/tenants/${encodeURIComponent(state.tenant)}/listings`, payload);
      if (alerts && alerts.length) {
        setStatus(`فایل ثبت شد و با ${number(alerts.length)} جست‌وجوی ذخیره‌شده جور است: ${alerts.map((alert) => alert.lead_name || alert.lead_contact || alert.search.name).join('، ')}`);
        await loadWorkspace();
        resetListingForm(form);
        return;
      }
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

$('#performance-form').addEventListener('submit', (event) => {
  event.preventDefault();
  renderPerformance();
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
  $('#cold-list').replaceChildren();
  $('#performance-report').replaceChildren();
  resetListingForm($('#listing-form'));
  document.querySelectorAll('.nav-item[data-view="team"]').forEach((item) => { item.hidden = false; });
  $('#connection-panel').hidden = false;
  $('#refresh').disabled = true;
  $('#disconnect').hidden = true;
  $('#office-name').textContent = 'دفتر متصل نشده';
  setStatus('اتصال قطع شد.');
});

function toggleFieldGroup(formSelector, attribute, value) {
  document.querySelectorAll(`${formSelector} [${attribute}]`).forEach((label) => {
    label.hidden = label.getAttribute(attribute) !== value;
  });
}

for (const selector of ['#budget-form', '#commission-form', '#search-form']) {
  const attribute = selector === '#budget-form' ? 'data-budget' : selector === '#commission-form' ? 'data-commission' : 'data-search';
  $(selector).elements.deal_type.addEventListener('change', (event) => toggleFieldGroup(selector, attribute, event.currentTarget.value));
}

$('#budget-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const data = fields(form);
  const result = $('#budget-result');
  try {
    const payload = {
      deal_type: data.deal_type,
      savings: parseAmount(String(data.savings || '')) || 0,
      monthly_income: parseAmount(String(data.monthly_income || '')),
    };
    if (data.deal_type === 'sale') payload.max_price = parseAmount(String(data.max_price || ''));
    else {
      payload.max_deposit = parseAmount(String(data.max_deposit || ''));
      payload.max_rent = parseAmount(String(data.max_rent || ''));
    }
    const answer = await api('POST', `/v1/tenants/${encodeURIComponent(state.tenant)}/budget`, payload);
    result.replaceChildren();
    if (answer.deal_type === 'sale') {
      result.append(element('p', '', `سقف بودجه: ${amount(answer.budget)} · آوردهٔ نقدی: ${amount(answer.savings)}`));
      result.append(element('p', '', answer.financed
        ? `بخش تأمین‌مالی‌شده: ${amount(answer.financed)} · قسط ماهانه با سود ${number(answer.annual_profit_rate * 100)}٪: ${amount(answer.monthly_payment)}`
        : 'با پول نقد فعلی، فایل بدون وام در دسترس است.'));
      if (answer.monthly_payment_share_of_income !== null) {
        result.append(element('p', '', `سهم قسط از درآمد ماهانه: ${percent(answer.monthly_payment_share_of_income)}`));
      }
    } else {
      result.append(element('p', '', `سقف رهن: ${amount(answer.max_deposit)} · سقف اجاره: ${amount(answer.max_rent)} · معادل رهنی: ${amount(answer.rahn_equivalent)}`));
      if (answer.deposit_gap) {
        result.append(element('p', '', `برای پرداخت رهن کامل ${amount(answer.deposit_gap)} کم دارید؛ با پول نقد فعلی، اجارهٔ حدود ${amount(answer.rent_with_savings)} در دسترس است.`));
      }
    }
    setStatus('محاسبه انجام شد.');
  } catch (error) {
    result.replaceChildren(empty(`محاسبه انجام نشد: ${error.message}`));
  }
});

$('#commission-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const data = fields(form);
  const result = $('#commission-result');
  try {
    const payload = { deal_type: data.deal_type };
    if (data.deal_type === 'sale') payload.price = parseAmount(String(data.price || ''));
    else payload.rent = parseAmount(String(data.rent || ''));
    const answer = await api('POST', `/v1/tenants/${encodeURIComponent(state.tenant)}/commission`, payload);
    result.replaceChildren(element('p', '', `کمیسیون کل: ${amount(answer.total)} · سهم هر طرف: ${amount(answer.per_side)}`));
  } catch (error) {
    result.replaceChildren(empty(`محاسبه انجام نشد: ${error.message}`));
  }
});

$('#convert-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const data = fields(form);
  const result = $('#convert-result');
  try {
    const answer = await api('POST', `/v1/tenants/${encodeURIComponent(state.tenant)}/convert-rahn`, {
      deposit: parseAmount(String(data.deposit)) || 0,
      rent: parseAmount(String(data.rent)) || 0,
    });
    result.replaceChildren(
      element('p', '', `معادل کل: ${amount(answer.rahn_equivalent)}`),
      element('p', '', `اگر همهٔ پول رهن شود: اجارهٔ صفر · اگر رهن صفر شود: اجارهٔ ${amount(answer.rent_if_deposit_is_zero)}`),
    );
  } catch (error) {
    result.replaceChildren(empty(`تبدیل انجام نشد: ${error.message}`));
  }
});

$('#compare-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const selected = new FormData(event.currentTarget).getAll('ids');
  const result = $('#compare-result');
  try {
    const { listings } = await api('GET', `/v1/tenants/${encodeURIComponent(state.tenant)}/compare?ids=${encodeURIComponent(selected.join(','))}`);
    result.replaceChildren();
    for (const listing of listings) {
      const row = element('div', 'lead-row');
      row.append(element('strong', '', listing.title));
      row.append(element('span', 'tag', listing.neighborhood));
      row.append(element('span', 'tag', listingLabel(listing)));
      row.append(element('span', 'tag', `${number(listing.bedrooms)} خواب`));
      if (listing.area) row.append(element('span', 'tag', `${number(listing.area)} متر`));
      if (listing.price_per_meter) row.append(element('span', 'tag', `متری ${amount(listing.price_per_meter)}`));
      if (listing.rent_per_meter) row.append(element('span', 'tag', `اجاره‌متری ${amount(listing.rent_per_meter)}`));
      row.append(element('span', 'tag', `${number(listing.freshness)} روز از آخرین به‌روزرسانی`));
      row.append(element('span', 'tag', listing.verified ? 'تأیید حضوری' : 'تأییدنشده'));
      result.append(row);
    }
  } catch (error) {
    result.replaceChildren(empty(`مقایسه انجام نشد: ${error.message}`));
  }
});

$('#trend-form').addEventListener('submit', (event) => {
  event.preventDefault();
  loadTrend(String(new FormData(event.currentTarget).get('neighborhood') || '').trim());
});

$('#search-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const data = fields(form);
  try {
    const payload = { name: String(data.name).trim(), deal_type: data.deal_type };
    const neighborhood = String(data.neighborhood || '').trim();
    if (neighborhood) payload.neighborhood = neighborhood;
    if (data.lead_id) payload.lead_id = data.lead_id;
    if (data.deal_type === 'sale') payload.max_price = parseAmount(String(data.max_price || ''));
    else {
      payload.max_deposit = parseAmount(String(data.max_deposit || ''));
      payload.max_rent = parseAmount(String(data.max_rent || ''));
    }
    await api('POST', `/v1/tenants/${encodeURIComponent(state.tenant)}/saved-searches`, payload);
    await loadWorkspace();
    form.reset();
    toggleFieldGroup('#search-form', 'data-search', 'sale');
    setStatus('جست‌وجوی ذخیره‌شده ساخته شد؛ از این به بعد فایل‌های جور هشدار می‌دهند.');
  } catch (error) {
    setStatus(`جست‌وجو ذخیره نشد: ${error.message}`, true);
  }
});

$('#today').textContent = new Intl.DateTimeFormat('fa-IR', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }).format(new Date());
