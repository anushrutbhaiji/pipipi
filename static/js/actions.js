function toggleDeleteMode() {
    isDeleteMode = !isDeleteMode;
    const table = document.getElementById('masterTable');
    const enterBtn = document.getElementById('enter-delete-mode-btn');
    const cancelBtn = document.getElementById('cancel-delete-mode-btn');
    const executeBtn = document.getElementById('bulk-delete-btn');

    if (isDeleteMode) {
        table.classList.add('delete-mode-active');
        if(enterBtn) enterBtn.style.display = 'none';
        if(cancelBtn) cancelBtn.style.display = 'block';
        if(executeBtn) executeBtn.style.display = 'block';
        updateDeleteButtonState(); 
    } else {
        table.classList.remove('delete-mode-active');
        if(enterBtn) enterBtn.style.display = 'block';
        if(cancelBtn) cancelBtn.style.display = 'none';
        if(executeBtn) executeBtn.style.display = 'none';
        
        const selectAll = document.getElementById('selectAllCheckbox');
        if(selectAll) selectAll.checked = false;
        document.querySelectorAll('.row-checkbox').forEach(cb => cb.checked = false);
    }
}

function toggleAllCheckboxes(source) {
    document.querySelectorAll('.row-checkbox').forEach(cb => cb.checked = source.checked);
    updateDeleteButtonState();
}

function updateDeleteButtonState() {
    const checkedCount = document.querySelectorAll('.row-checkbox:checked').length;
    const btn = document.getElementById('bulk-delete-btn');
    
    if (btn && isDeleteMode) {
        btn.innerText = `🗑️ Delete Selected (${checkedCount})`;
        if (checkedCount > 0) {
            btn.disabled = false;
            btn.style.opacity = '1';
            btn.style.cursor = 'pointer';
        } else {
            btn.disabled = true;
            btn.style.opacity = '0.5';
            btn.style.cursor = 'not-allowed';
            const selectAll = document.getElementById('selectAllCheckbox');
            if(selectAll) selectAll.checked = false;
        }
    }
}

function openDeleteModal() {
    console.log("Opening modal...");
    const checkedCount = document.querySelectorAll('.row-checkbox:checked').length;
    if (checkedCount === 0) {
        alert("⚠️ Please check at least one box first.");
        return;
    }

    const modal = document.getElementById('deleteModal');
    if (!modal) {
        alert("❌ ERROR: The <div id='deleteModal'> HTML is missing from inventory.html!");
        return;
    }
    
    document.getElementById('delete-count-text').innerText = checkedCount;
    const inputEl = document.getElementById('deleteConfirmInput');
    if (inputEl) inputEl.value = ''; 
    
    checkDeleteInput(); 
    modal.style.display = 'flex';
    if (inputEl) inputEl.focus();
}

function closeDeleteModal() {
    const modal = document.getElementById('deleteModal');
    if(modal) modal.style.display = 'none';
}

function checkDeleteInput() {
    const inputEl = document.getElementById('deleteConfirmInput');
    const btn = document.getElementById('confirmDeleteBtn');
    if (!inputEl || !btn) return; 

    if (inputEl.value.trim().toUpperCase() === 'REJECT') {
        btn.disabled = false;
        btn.style.opacity = '1';
        btn.style.cursor = 'pointer';
    } else {
        btn.disabled = true;
        btn.style.opacity = '0.5';
        btn.style.cursor = 'not-allowed';
    }
}

async function executeBulkDelete() {
    const ids = Array.from(document.querySelectorAll('.row-checkbox:checked')).map(cb => parseInt(cb.value));
    if (ids.length === 0) return;

    const btn = document.getElementById('confirmDeleteBtn');
    btn.innerText = "Deleting...";
    btn.disabled = true;

    try {
        let requestHeaders = { 'Content-Type': 'application/json' };
        if (typeof AUTH_HEADER !== 'undefined') requestHeaders = { ...requestHeaders, ...AUTH_HEADER };

        const res = await fetch('/api/inventory/reject', {
            method: 'POST',
            headers: requestHeaders,
            body: JSON.stringify({ ids: ids })
        });
        
        const data = await res.json();
        
        if (data.success) {
            closeDeleteModal();
            toggleDeleteMode(); 
            fetchInventory(typeof currentPage !== 'undefined' ? currentPage : 1); 
        } else {
            alert("❌ Server Error: " + data.message);
            btn.innerText = "Delete Forever";
            checkDeleteInput();
        }
    } catch (e) {
        console.error(e);
        alert("Failed to connect to server.");
        btn.innerText = "Delete Forever";
        checkDeleteInput();
    }
}