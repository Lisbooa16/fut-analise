document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.alert').forEach(a => setTimeout(() => a.classList.add('fade-out'), 3000));
});
