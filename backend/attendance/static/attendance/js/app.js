document.addEventListener('click', (event) => {
    const trigger = event.target.closest('[data-table-search]');
    if (!trigger) return;
    const input = document.querySelector(trigger.dataset.tableSearch);
    if (input) input.focus();
});
