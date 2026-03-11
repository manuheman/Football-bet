document.addEventListener('DOMContentLoaded', function () {
    const countrySelect = document.querySelector('#id_country');
    const leagueSelect = document.querySelector('#id_league');
    if (!countrySelect || !leagueSelect) return;

    const leagueChoices = {
        'england': ['Premier League', 'FA Cup', 'Championship'],
        'germany': ['DFB Pocal', 'Bundesliga1', 'Bundesliga2'],
        'spain': ['La Liga', 'Segunda Division'],
        'italy': ['Coppa Italia', 'Serie A', 'Serie B'],
        'russia': ['Russia Cup', 'Russia Premier League'],
        'france': ['Coupe de France', 'France League 1'],
        'netherlands': ['Eredivisie'],
        'portugal': ['Premier League'],
        'switzerland': ['Super League'],
        'saudi arabia': ['Professional League'],
        'ethiopia': ['Premier League'],
        'scotland': ['Premier League'],
        'ukraine': ['Premier League'],
        'south africa': ['Premier League']
    };

    function updateLeague() {
        const country = countrySelect.value.toLowerCase(); // lowercase key
        const leagues = leagueChoices[country] || [];
        const currentValue = leagueSelect.value;

        leagueSelect.innerHTML = '';
        leagues.forEach(l => {
            const option = document.createElement('option');
            option.value = l;
            option.text = l;
            leagueSelect.appendChild(option);
        });

        if (currentValue && [...leagueSelect.options].some(o => o.value === currentValue)) {
            leagueSelect.value = currentValue;
        }
    }

    updateLeague();
    countrySelect.addEventListener('change', updateLeague);
});