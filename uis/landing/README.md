# TrackFlow Landing + Formulario

Proyecto frontend estático de TrackFlow con:

- Landing comercial
- Formulario de solicitud para empresas
- Estilos con Tailwind CSS compilado localmente para la landing

## Demo pública

- URL: https://landingtrackflow.rubenlosada.com/

## Estructura

```text
landing/
├── index.html
├── tailwind.css
├── tailwind.input.css
├── icon/
├── logo/
├── images/
└── formulario/
    ├── index.html
    ├── application.html
    └── validation.js
```

## Rutas clave

- Landing principal: `./index.html`
- Formulario: `./formulario/application.html`
- Redirección corta a formulario: `./formulario/index.html`

## Ejecución local

Desde la carpeta `uis/landing` puedes servir archivos estáticos con:

```bash
npx serve .
```

Luego abre la URL local que te muestre la terminal.

## PageSpeed (producción)

Resultados reportados para https://landingtrackflow.rubenlosada.com/:

- Performance: 93
- Accessibility: 100
- Best Practices: 96
- SEO: 100

Nota: en este entorno no he podido recuperar automáticamente esos valores desde la API pública de PageSpeed porque devolvió límite de cuota (HTTP 429).
