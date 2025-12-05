// script.js

// Crea mappa centrata sull'area universitaria
var map = L.map('map').setView([40.77195, 14.7907], 16);

// Basemap OpenStreetMap
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors'
}).addTo(map);

// ----- Layer strade come sfondo -----
var stradeLayer;
var stradePath = "strade_clip_Convertito.gpkg";
fetch(stradePath)
    .then(resp => resp.json())
    .then(data => {
        stradeLayer = L.geoJSON(data, {color:'grey', weight:2}).addTo(map);
    })
    .catch(err => console.error("Errore caricamento strade:", err));

// ----- Variabili per punti e percorsi -----
var startMarker = null;
var endMarker = null;
var line = null;
var geojsonSole = null;
var geojsonOmbra = null;

// Funzione per fare "snap" ai nodi stradali più vicini
function snapToStrade(latlng) {
    if(!stradeLayer) return latlng;

    var closest = null;
    var minDist = Infinity;

    stradeLayer.eachLayer(function(layer){
        if(layer.feature.geometry.type === "LineString"){
            var coords = layer.feature.geometry.coordinates;
            coords.forEach(function(c){
                var dist = map.distance(latlng, L.latLng(c[1], c[0]));
                if(dist < minDist){
                    minDist = dist;
                    closest = L.latLng(c[1], c[0]);
                }
            });
        }
    });

    return closest || latlng;
}

// Gestione click mappa
map.on('click', function(e){
    if(!startMarker){
        var snapped = snapToStrade(e.latlng);
        startMarker = L.marker(snapped, {draggable:true}).addTo(map).bindPopup("Partenza").openPopup();
    } else if(!endMarker){
        var snapped = snapToStrade(e.latlng);
        endMarker = L.marker(snapped, {draggable:true}).addTo(map).bindPopup("Arrivo").openPopup();

        line = L.polyline([startMarker.getLatLng(), endMarker.getLatLng()], {color:'red', weight:3}).addTo(map);
        map.fitBounds(line.getBounds());
    } else {
        map.removeLayer(startMarker);
        map.removeLayer(endMarker);
        if(line) map.removeLayer(line);
        startMarker = null; endMarker = null; line = null;
        alert("Seleziona di nuovo i punti di partenza e arrivo");
    }
});

// Funzione per calcolare percorso tramite Flask
function calcolaPercorsoAPI(){
    if(!startMarker || !endMarker){
        alert("Seleziona i punti di partenza e arrivo");
        return;
    }

    var data = {
        start_lon: startMarker.getLatLng().lng,
        start_lat: startMarker.getLatLng().lat,
        end_lon: endMarker.getLatLng().lng,
        end_lat: endMarker.getLatLng().lat
    };

    fetch("http://127.0.0.1:8002/percorsi", {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body: JSON.stringify(data)
    })
    .then(res => res.json())
    .then(data => {
        // Rimuovi percorsi precedenti
        if(geojsonSole) map.removeLayer(geojsonSole);
        if(geojsonOmbra) map.removeLayer(geojsonOmbra);
        geojsonSole = null; geojsonOmbra = null;

        var layers = [];

        if(data.sole && data.sole.features.length>0){
            geojsonSole = L.geoJSON(data.sole, {color:'orange', weight:5}).addTo(map);
            layers.push(geojsonSole);
        }
        if(data.ombra && data.ombra.features.length>0){
            geojsonOmbra = L.geoJSON(data.ombra, {color:'blue', weight:5}).addTo(map);
            layers.push(geojsonOmbra);
        }

        if(layers.length>0){
            map.fitBounds(L.featureGroup(layers).getBounds());
        } else {
            alert("Percorso non trovato!");
        }
    })
    .catch(err => alert("Errore calcolo percorso: " + err));
}

// Collega pulsante
document.getElementById('loadPath').addEventListener('click', calcolaPercorsoAPI);
