(() => {
  const toggle = document.getElementById('mobile-toggle');
  const menu = document.getElementById('mobile-menu');

  if (toggle && menu) {
    const setMenuOpen = (open) => {
      toggle.setAttribute('aria-expanded', String(open));
      toggle.setAttribute('aria-label', open ? 'إغلاق قائمة التنقل' : 'فتح قائمة التنقل');
      menu.hidden = !open;
    };
    toggle.addEventListener('click', () => setMenuOpen(toggle.getAttribute('aria-expanded') !== 'true'));
    menu.querySelectorAll('a').forEach((link) => link.addEventListener('click', () => setMenuOpen(false)));
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && !menu.hidden) {
        setMenuOpen(false);
        toggle.focus();
      }
    });
  }

  const lightbox = document.getElementById('gallery-lightbox');
  if (lightbox && typeof lightbox.showModal === 'function') {
    const image = document.getElementById('gallery-lightbox-image');
    const caption = document.getElementById('gallery-lightbox-caption');
    document.querySelectorAll('[data-gallery-open]').forEach((button) => {
      button.addEventListener('click', () => {
        image.src = button.dataset.image;
        image.alt = button.getAttribute('aria-label') || '';
        caption.textContent = button.dataset.caption || '';
        lightbox.showModal();
      });
    });
    lightbox.querySelector('[data-gallery-close]')?.addEventListener('click', () => lightbox.close());
    lightbox.addEventListener('click', (event) => {
      if (event.target === lightbox) lightbox.close();
    });
    lightbox.addEventListener('close', () => {
      image.removeAttribute('src');
      caption.textContent = '';
    });
  }

  const enrollmentDialog = document.getElementById('request-enroll-modal');
  const enrollmentForm = document.getElementById('request-enroll-form');
  if (enrollmentDialog && enrollmentForm && typeof enrollmentDialog.showModal === 'function') {
    document.querySelectorAll('[data-enrollment-request]').forEach((button) => {
      button.addEventListener('click', () => {
        enrollmentForm.action = `/trainee/batches/${encodeURIComponent(button.dataset.batchId)}/request`;
        document.getElementById('modal-course-name').textContent = button.dataset.courseName || '';
        document.getElementById('modal-batch-name').textContent = button.dataset.batchName || '';
        enrollmentDialog.showModal();
      });
    });
    enrollmentDialog.querySelectorAll('[data-dialog-close]').forEach((button) => {
      button.addEventListener('click', () => enrollmentDialog.close());
    });
  }
})();
