(() => {
  const icon = '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="11" height="11" rx="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>';

  async function copy(value) {
    try {
      await navigator.clipboard.writeText(value);
    } catch {
      const area = document.createElement('textarea');
      area.value = value;
      area.style.position = 'fixed';
      area.style.opacity = '0';
      document.body.append(area);
      area.select();
      document.execCommand('copy');
      area.remove();
    }
  }

  document.querySelectorAll('pre').forEach((pre) => {
    if (pre.dataset.copyButton || pre.parentElement?.querySelector(':scope > .copy-code')) return;
    pre.dataset.copyButton = 'true';
    const sample = document.createElement('div');
    sample.className = 'code-sample';
    pre.before(sample);
    sample.append(pre);
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'copy-code';
    button.setAttribute('aria-label', 'Copy code example');
    button.title = 'Copy code';
    button.innerHTML = icon;
    button.addEventListener('click', async () => {
      await copy(pre.textContent || '');
      button.classList.add('copied');
      button.title = 'Copied';
      window.setTimeout(() => {
        button.classList.remove('copied');
        button.title = 'Copy code';
      }, 1400);
    });
    sample.append(button);
  });
})();
