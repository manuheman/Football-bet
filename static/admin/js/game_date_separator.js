document.addEventListener('DOMContentLoaded', function() {
    const tbody = document.querySelector('#result_list tbody');
    if (!tbody) return;
    const rows = Array.from(tbody.querySelectorAll('tr'));
    let previousDate = null;
    let dayRows = [];
    rows.forEach(row => {
        const cells = row.querySelectorAll('td');
        if (cells.length >= 15) {
            const dateText = cells[14].textContent.trim();
            const date = dateText.split(' ')[0];
            if (previousDate && date !== previousDate) {
                // insert hr with checkbox for previous day
                const hrRow = document.createElement('tr');
                const hrCell = document.createElement('td');
                hrCell.colSpan = cells.length;
                hrCell.innerHTML = '<div style="text-align: center; padding: 5px;"><label><input type="checkbox" id="select_' + previousDate.replace(/-/g, '_') + '"> Select all for ' + previousDate + '</label><hr style="border: none; border-top: 1px solid #ccc; margin: 5px 0;"></div>';
                tbody.insertBefore(hrRow, row);
                // add event listener
                document.getElementById('select_' + previousDate.replace(/-/g, '_')).addEventListener('change', function() {
                    dayRows.forEach(r => {
                        const cb = r.querySelector('input[type="checkbox"][name="_selected_action"]');
                        if (cb) cb.checked = this.checked;
                    });
                });
                dayRows = [];
            }
            dayRows.push(row);
            previousDate = date;
        }
    });
    // for the last day
    if (dayRows.length > 0 && previousDate) {
        const hrRow = document.createElement('tr');
        const hrCell = document.createElement('td');
        hrCell.colSpan = rows[0].querySelectorAll('td').length;
        hrCell.innerHTML = '<div style="text-align: center; padding: 5px;"><label><input type="checkbox" id="select_' + previousDate.replace(/-/g, '_') + '"> Select all for ' + previousDate + '</label><hr style="border: none; border-top: 1px solid #ccc; margin: 5px 0;"></div>';
        tbody.appendChild(hrRow);
        document.getElementById('select_' + previousDate.replace(/-/g, '_')).addEventListener('change', function() {
            dayRows.forEach(r => {
                const cb = r.querySelector('input[type="checkbox"][name="_selected_action"]');
                if (cb) cb.checked = this.checked;
            });
        });
    }
});