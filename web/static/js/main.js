/* =========================================================
   AFAQ ACADEMY — MAIN JAVASCRIPT
   ========================================================= */

// ---------------------------------------------------------
// SIDEBAR TOGGLE (Mobile)
// ---------------------------------------------------------
(function () {
  const toggle = document.getElementById('sidebar-toggle');
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebar-overlay');

  function openSidebar() {
    sidebar && sidebar.classList.add('open');
    overlay && overlay.classList.add('open');
    document.body.style.overflow = 'hidden';
  }

  function closeSidebar() {
    sidebar && sidebar.classList.remove('open');
    overlay && overlay.classList.remove('open');
    document.body.style.overflow = '';
  }

  toggle && toggle.addEventListener('click', openSidebar);
  overlay && overlay.addEventListener('click', closeSidebar);
})();

// ---------------------------------------------------------
// PASSWORD SHOW/HIDE
// ---------------------------------------------------------
document.querySelectorAll('[data-show-password]').forEach(function (btn) {
  btn.addEventListener('click', function () {
    const target = document.getElementById(btn.dataset.showPassword);
    if (!target) return;
    if (target.type === 'password') {
      target.type = 'text';
      btn.innerHTML = eyeOffIcon();
    } else {
      target.type = 'password';
      btn.innerHTML = eyeIcon();
    }
  });
});

function eyeIcon() {
  return '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path stroke-linecap="round" stroke-linejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>';
}

function eyeOffIcon() {
  return '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21"/></svg>';
}

// ---------------------------------------------------------
// MODAL
// ---------------------------------------------------------
window.openModal = function (id) {
  const el = document.getElementById(id);
  el && el.classList.add('open');
};

window.closeModal = function (id) {
  const el = document.getElementById(id);
  el && el.classList.remove('open');
};

document.querySelectorAll('[data-modal-open]').forEach(function (btn) {
  btn.addEventListener('click', function () { openModal(btn.dataset.modalOpen); });
});

document.querySelectorAll('[data-modal-close]').forEach(function (btn) {
  btn.addEventListener('click', function () { closeModal(btn.dataset.modalClose); });
});

// Close modal on overlay click
document.querySelectorAll('.modal-overlay').forEach(function (overlay) {
  overlay.addEventListener('click', function (e) {
    if (e.target === overlay) overlay.classList.remove('open');
  });
});

// ---------------------------------------------------------
// TOAST NOTIFICATIONS
// ---------------------------------------------------------
window.showToast = function (message, type) {
  type = type || 'success';
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = 'toast ' + type;
  toast.innerHTML = (type === 'success'
    ? '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>'
    : '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>'
  ) + '<span class="toast-text">' + message + '</span>';

  container.appendChild(toast);

  setTimeout(function () {
    toast.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
    setTimeout(function () { toast.remove(); }, 350);
  }, 3500);
};

// Auto-show flash messages as toasts
document.addEventListener('DOMContentLoaded', function () {
  const flashMessages = document.querySelectorAll('[data-flash]');
  flashMessages.forEach(function (el) {
    showToast(el.dataset.flashMessage, el.dataset.flashType);
  });
});

// ---------------------------------------------------------
// LIVE TABLE SEARCH
// ---------------------------------------------------------
document.querySelectorAll('[data-search-table]').forEach(function (input) {
  const tableId = input.dataset.searchTable;
  const table = document.getElementById(tableId);
  if (!table) return;

  input.addEventListener('input', function () {
    const query = input.value.toLowerCase().trim();
    const rows = table.querySelectorAll('tbody tr');
    let visible = 0;

    rows.forEach(function (row) {
      const text = row.textContent.toLowerCase();
      const match = text.includes(query);
      row.style.display = match ? '' : 'none';
      if (match) visible++;
    });

    // Show/hide empty state
    const emptyRow = table.querySelector('.empty-row');
    if (emptyRow) {
      emptyRow.style.display = visible === 0 ? '' : 'none';
    }
  });
});

// ---------------------------------------------------------
// FORM LOADING STATE
// ---------------------------------------------------------
document.querySelectorAll('form[data-loading]').forEach(function (form) {
  form.addEventListener('submit', function () {
    const btn = form.querySelector('[type="submit"]');
    if (!btn) return;
    btn.disabled = true;
    const original = btn.innerHTML;
    btn.dataset.originalText = original;
    btn.innerHTML = '<span class="spinner"></span> ' + (btn.dataset.loadingText || 'Saving...');
  });
});

// ---------------------------------------------------------
// CONFIRM DIALOG (inline confirm buttons)
// ---------------------------------------------------------
document.querySelectorAll('[data-confirm]').forEach(function (btn) {
  btn.addEventListener('click', function (e) {
    const msg = btn.dataset.confirm || 'Are you sure?';
    if (!confirm(msg)) {
      e.preventDefault();
      e.stopPropagation();
    }
  });
});

// ---------------------------------------------------------
// ATTENDANCE: STATUS COLOR
// ---------------------------------------------------------
document.querySelectorAll('.status-select').forEach(function (sel) {
  function updateColor() {
    sel.className = 'status-select form-select';
    if (sel.value === 'present') sel.classList.add('status-present');
    if (sel.value === 'absent')  sel.classList.add('status-absent');
  }
  updateColor();
  sel.addEventListener('change', updateColor);
});

// ---------------------------------------------------------
// SCORE: GRADE COLOR
// ---------------------------------------------------------
function gradeClass(score) {
  if (score >= 90) return 'grade-A';
  if (score >= 80) return 'grade-B';
  if (score >= 70) return 'grade-C';
  if (score >= 60) return 'grade-D';
  return 'grade-F';
}

document.querySelectorAll('.score-input').forEach(function (inp) {
  function updatePreview() {
    const preview = inp.closest('tr').querySelector('.grade-preview');
    if (!preview) return;
    const val = parseFloat(inp.value);
    if (isNaN(val) || val < 0 || val > 100) {
      preview.textContent = '--';
      preview.className = 'grade-letter';
    } else {
      const g = val >= 90 ? 'A' : val >= 80 ? 'B' : val >= 70 ? 'C' : val >= 60 ? 'D' : 'F';
      preview.textContent = g;
      preview.className = 'grade-letter ' + gradeClass(val);
    }
  }
  updatePreview();
  inp.addEventListener('input', updatePreview);
});
