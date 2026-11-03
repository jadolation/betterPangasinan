/* Change providers here, never in coordinate extraction or display logic. */
window.ProjectMapProviders = Object.freeze({
  defaultBasemap: 'osm',
  osm: Object.freeze({
    url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>',
    updateWhenIdle: true,
    keepBuffer: 0,
  }),
});
