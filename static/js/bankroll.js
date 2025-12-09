document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('bankrollForm');

  if (form) {
    const buttons = form.querySelectorAll('button[type="submit"]');
    let lastClickedBtn = null;

    // Rastreia qual botão foi clicado
    buttons.forEach(btn => {
      btn.addEventListener('click', () => {
        lastClickedBtn = btn;
      });
    });

    form.addEventListener('submit', (e) => {
      if (!lastClickedBtn) return;

      // --- CORREÇÃO PRINCIPAL AQUI ---
      // Como vamos desabilitar o botão, precisamos criar um input hidden
      // para garantir que o valor (increase/remove) seja enviado ao Django.
      const hiddenInput = document.createElement('input');
      hiddenInput.type = 'hidden';
      hiddenInput.name = lastClickedBtn.name; // 'action'
      hiddenInput.value = lastClickedBtn.value; // 'increase' ou 'remove'
      form.appendChild(hiddenInput);
      // -------------------------------

      const btnType = lastClickedBtn.getAttribute('data-type');

      // Efeito visual (Spinner)
      const loadingText = btnType === 'add' ? 'Depositando...' : 'Sacando...';
      lastClickedBtn.innerHTML = `
        <span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
        ${loadingText}
      `;

      // Agora podemos desabilitar sem perder o dado (pois criamos o hidden input)
      buttons.forEach(b => b.disabled = true);
    });
  }
});
