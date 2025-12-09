// script.js

// -------------------------------------------------------
// MAPPA
// -------------------------------------------------------
var map = L.map('map').setView([40.77195, 14.7907], 16);

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors'
}).addTo(map);

// -------------------------------------------------------
// CARICA LAYER STRADE
// -------------------------------------------------------
var stradeLayer;
var stradePath = "strade_clip_Convertito.gpkg";

fetch(stradePath)
    .then(resp => resp.json())
    .then(data => {
        stradeLayer = L.geoJSON(data, { color: 'grey', weight: 2 }).addTo(map);
    })
    .catch(err => console.error("Errore caricamento strade:", err));

// -------------------------------------------------------
// VARIABILI GLOBALI
// -------------------------------------------------------
var startMarker = null;
var endMarker = null;
var line = null;
var geojsonSole = null;
var geojsonOmbra = null;

// -------------------------------------------------------
// FUNZIONE SNAP
// -------------------------------------------------------
function snapToStrade(latlng) {
    if (!stradeLayer) return latlng;

    var closest = null;
    var minDist = Infinity;

    stradeLayer.eachLayer(function (layer) {
        if (layer.feature.geometry.type === "LineString") {
            var coords = layer.feature.geometry.coordinates;
            coords.forEach(function (c) {
                var dist = map.distance(latlng, L.latLng(c[1], c[0]));
                if (dist < minDist) {
                    minDist = dist;
                    closest = L.latLng(c[1], c[0]);
                }
            });
        }
    });

    return closest || latlng;
}

// -------------------------------------------------------
// CLICK SULLA MAPPA
// -------------------------------------------------------
map.on('click', function (e) {
    if (!startMarker) {
        var snapped = snapToStrade(e.latlng);
        startMarker = L.marker(snapped, { draggable: true }).addTo(map).bindPopup("Partenza").openPopup();

    } else if (!endMarker) {
        var snapped = snapToStrade(e.latlng);
        endMarker = L.marker(snapped, { draggable: true }).addTo(map).bindPopup("Arrivo").openPopup();

        line = L.polyline([startMarker.getLatLng(), endMarker.getLatLng()], { color: 'red', weight: 3 }).addTo(map);
        map.fitBounds(line.getBounds());

    } else {
        map.removeLayer(startMarker);
        map.removeLayer(endMarker);
        if (line) map.removeLayer(line);

        startMarker = null;
        endMarker = null;
        line = null;
        alert("Seleziona di nuovo i punti di partenza e arrivo");
    }
});

// -------------------------------------------------------
// CHIAMATA API CON SCELTA STAGIONE / FASCIA / TIPO
// -------------------------------------------------------
function calcolaPercorsoAPI() {

    if (!startMarker || !endMarker) {
        alert("Seleziona i punti di partenza e arrivo");
        return;
    }

    // 🔥 valori presi dalla UI
    var stagione = document.getElementById("stagione").value;
    var fascia = document.getElementById("fascia").value;
    var tipo = document.getElementById("tipo").value;  

    var data = {
        start_lon: startMarker.getLatLng().lng,
        start_lat: startMarker.getLatLng().lat,
        end_lon: endMarker.getLatLng().lng,
        end_lat: endMarker.getLatLng().lat,
        stagione: stagione,
        fascia: fascia,
        tipo: tipo
    };

    fetch("http://127.0.0.1:8002/percorsi", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data)
    })
        .then(res => res.json())
        .then(data => {

            // Ripulisci percorsi vecchi
            if (geojsonSole) map.removeLayer(geojsonSole);
            if (geojsonOmbra) map.removeLayer(geojsonOmbra);
            geojsonSole = null;
            geojsonOmbra = null;

            var layers = [];

            // Mostra solo quello scelto
            if (tipo === "sole" && data.sole && data.sole.features.length > 0) {
                geojsonSole = L.geoJSON(data.sole, { color: 'orange', weight: 5 }).addTo(map);
                layers.push(geojsonSole);
            }

            if (tipo === "ombra" && data.ombra && data.ombra.features.length > 0) {
                geojsonOmbra = L.geoJSON(data.ombra, { color: 'blue', weight: 5 }).addTo(map);
                layers.push(geojsonOmbra);
            }

            if (layers.length > 0) {
                map.fitBounds(L.featureGroup(layers).getBounds());
            } else {
                alert("Percorso non trovato!");
            }
        })
        .catch(err => alert("Errore calcolo percorso: " + err));
}

// Bottone
document.getElementById('loadPath').addEventListener('click', calcolaPercorsoAPI);
