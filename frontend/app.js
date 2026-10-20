const views = {
  overview: 'نمای کلی',
  inbox: 'صندوق مکالمات',
  listings: 'فایل‌ها و تطبیق',
  team: 'عملکرد مشاوران',
  reports: 'گزارش پایلوت'
};

const pageTitle = document.querySelector('#page-title');
const navItems = document.querySelectorAll('.nav-item[data-view]');
const viewNodes = document.querySelectorAll('.view');

function showView(name) {
  if (!views[name]) return;
  navItems.forEach((item) => item.classList.toggle('active', item.dataset.view === name));
  viewNodes.forEach((view) => view.classList.toggle('active-view', view.id === `${name}-view`));
  pageTitle.textContent = views[name];
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

document.querySelectorAll('[data-view]').forEach((control) => {
  control.addEventListener('click', () => showView(control.dataset.view));
});

document.querySelector('#capture-open').addEventListener('click', () => {
  document.querySelector('#capture-modal').classList.add('open');
  document.querySelector('#lead-name').focus();
});

document.querySelector('#capture-close').addEventListener('click', () => {
  document.querySelector('#capture-modal').classList.remove('open');
});

document.querySelector('#capture-modal').addEventListener('click', (event) => {
  if (event.target.id === 'capture-modal') event.currentTarget.classList.remove('open');
});

document.querySelector('#save-lead').addEventListener('click', () => {
  document.querySelector('#capture-modal').classList.remove('open');
  document.querySelector('#toast').classList.add('show');
  setTimeout(() => document.querySelector('#toast').classList.remove('show'), 2800);
});

document.querySelectorAll('.filter').forEach((filter) => {
  filter.addEventListener('click', () => {
    document.querySelectorAll('.filter').forEach((item) => item.classList.remove('active'));
    filter.classList.add('active');
  });
});

document.querySelectorAll('.conversation').forEach((conversation) => {
  conversation.addEventListener('click', () => {
    document.querySelectorAll('.conversation').forEach((item) => item.classList.remove('selected'));
    conversation.classList.add('selected');
  });
});
