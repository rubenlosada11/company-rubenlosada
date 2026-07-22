const form = document.getElementById("applicationForm");
const successMessage = document.getElementById("successMessage");
const volumeWarning = document.getElementById("volumeWarning");
const comentarios = document.getElementById("comentarios");
const comentariosCounter = document.getElementById("comentariosCounter");

if (!form) throw new Error("No se encontro el formulario applicationForm");

const trackedFields = [
  "nombreEmpresa",
  "personaContacto",
  "emailCorporativo",
  "telefono",
  "sitioWeb",
  "paisOperacion",
  "tipoProducto",
  "volumenMensual",
  "comentarios",
  "aceptoPrivacidad",
  "tresplActual",
  "serviciosInteres",
];

function getField(id) {
  return document.getElementById(id);
}

function getError(id) {
  return document.getElementById(`${id}Error`);
}

function setError(id, message) {
  const el = getError(id);
  if (!el) return;
  if (!message) {
    el.textContent = "";
    el.classList.add("hidden");
    return;
  }
  el.textContent = message;
  el.classList.remove("hidden");
}

function setInputState(input, isValid) {
  if (!input) return;
  input.classList.remove("border-rose-500", "focus:border-rose-500", "focus:ring-rose-200");
  input.classList.remove("border-emerald-500", "focus:border-emerald-500", "focus:ring-emerald-200");

  if (isValid) {
    input.classList.add("border-emerald-500", "focus:border-emerald-500", "focus:ring-emerald-200");
    input.setAttribute("aria-invalid", "false");
  } else {
    input.classList.add("border-rose-500", "focus:border-rose-500", "focus:ring-rose-200");
    input.setAttribute("aria-invalid", "true");
  }
}

function validateNombreEmpresa() {
  const field = getField("nombreEmpresa");
  const value = field.value.trim();
  const msg = value.length >= 2 ? "" : "El nombre de la empresa debe tener al menos 2 caracteres";
  setError("nombreEmpresa", msg);
  setInputState(field, !msg);
  return !msg;
}

function validatePersonaContacto() {
  const field = getField("personaContacto");
  const words = field.value.trim().split(/\s+/).filter(Boolean);
  const msg = words.length >= 2 ? "" : "Ingresa nombre y apellido del contacto";
  setError("personaContacto", msg);
  setInputState(field, !msg);
  return !msg;
}

function validateEmailCorporativo() {
  const field = getField("emailCorporativo");
  const value = field.value.trim();
  const re = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
  const msg = re.test(value) ? "" : "Ingresa un email corporativo válido (ejemplo: <nombre@empresa.com>)";
  setError("emailCorporativo", msg);
  setInputState(field, !msg);
  return !msg;
}

function validateTelefono() {
  const field = getField("telefono");
  const value = field.value.trim();
  const re = /^\+\d{1,3}[\s\d]{6,20}$/;
  const msg = re.test(value) ? "" : "El teléfono debe incluir código de país (ejemplo: +1 213 555 0147)";
  setError("telefono", msg);
  setInputState(field, !msg);
  return !msg;
}

function validateSitioWeb() {
  const field = getField("sitioWeb");
  const value = field.value.trim();
  if (!value) {
    setError("sitioWeb", "");
    setInputState(field, true);
    return true;
  }
  const re = /^https?:\/\/.+/i;
  const msg = re.test(value) ? "" : "Si incluyes sitio web, debe ser una URL válida";
  setError("sitioWeb", msg);
  setInputState(field, !msg);
  return !msg;
}

function validatePaisOperacion() {
  const field = getField("paisOperacion");
  const msg = field.value ? "" : "Selecciona el país de operación principal";
  setError("paisOperacion", msg);
  setInputState(field, !msg);
  return !msg;
}

function validateTipoProducto() {
  const field = getField("tipoProducto");
  const msg = field.value ? "" : "Selecciona el tipo de producto que manejas";
  setError("tipoProducto", msg);
  setInputState(field, !msg);
  return !msg;
}

function validateVolumenMensual() {
  const field = getField("volumenMensual");
  const msg = field.value ? "" : "Selecciona el volumen mensual estimado";
  setError("volumenMensual", msg);
  setInputState(field, !msg);
  return !msg;
}

function validateServiciosInteres() {
  const boxes = Array.from(document.querySelectorAll('input[name="serviciosInteres"]'));
  const oneChecked = boxes.some((box) => box.checked);
  const msg = oneChecked ? "" : "Selecciona al menos un servicio de interés";
  setError("serviciosInteres", msg);
  boxes.forEach((box) => box.setAttribute("aria-invalid", oneChecked ? "false" : "true"));
  return oneChecked;
}

function validateTresplActual() {
  const radios = Array.from(document.querySelectorAll('input[name="tresplActual"]'));
  const checked = radios.some((r) => r.checked);
  const msg = checked ? "" : "Indica si actualmente trabajas con otro proveedor logístico";
  setError("tresplActual", msg);
  radios.forEach((radio) => radio.setAttribute("aria-invalid", checked ? "false" : "true"));
  return checked;
}

function validateComentarios() {
  const field = getField("comentarios");
  const remaining = 500 - field.value.length;
  comentariosCounter.textContent = `${remaining} caracteres restantes`;

  if (remaining < 0) {
    const msg = `Los comentarios no pueden exceder 500 caracteres (quedan ${remaining})`;
    setError("comentarios", msg);
    setInputState(field, false);
    return false;
  }

  setError("comentarios", "");
  setInputState(field, true);
  return true;
}

function validateAceptoPrivacidad() {
  const field = getField("aceptoPrivacidad");
  const msg = field.checked ? "" : "Debes aceptar la política de privacidad para continuar";
  setError("aceptoPrivacidad", msg);
  field.setAttribute("aria-invalid", field.checked ? "false" : "true");
  return field.checked;
}

function evaluateLowVolumeWarning() {
  const volumen = getField("volumenMensual").value;
  const tipoProducto = getField("tipoProducto").value;
  const showWarning = volumen === "0-100" && !!tipoProducto;

  if (showWarning) {
    volumeWarning.classList.remove("hidden");
  } else {
    volumeWarning.classList.add("hidden");
  }
}

function validateAll() {
  const validations = [
    validateNombreEmpresa(),
    validatePersonaContacto(),
    validateEmailCorporativo(),
    validateTelefono(),
    validateSitioWeb(),
    validatePaisOperacion(),
    validateTipoProducto(),
    validateVolumenMensual(),
    validateServiciosInteres(),
    validateTresplActual(),
    validateComentarios(),
    validateAceptoPrivacidad(),
  ];

  evaluateLowVolumeWarning();
  return validations.every(Boolean);
}

function bindValidation() {
  const directValidationMap = {
    nombreEmpresa: validateNombreEmpresa,
    personaContacto: validatePersonaContacto,
    emailCorporativo: validateEmailCorporativo,
    telefono: validateTelefono,
    sitioWeb: validateSitioWeb,
    paisOperacion: validatePaisOperacion,
    tipoProducto: validateTipoProducto,
    volumenMensual: validateVolumenMensual,
    comentarios: validateComentarios,
    aceptoPrivacidad: validateAceptoPrivacidad,
  };

  Object.entries(directValidationMap).forEach(([id, fn]) => {
    const field = getField(id);
    if (!field) return;
    const primaryEvent = field.type === "checkbox" || field.tagName === "SELECT" ? "change" : "input";

    field.addEventListener(primaryEvent, () => {
      fn();
      evaluateLowVolumeWarning();
      successMessage.classList.add("hidden");
    });

    field.addEventListener("blur", () => {
      fn();
      evaluateLowVolumeWarning();
    });
  });

  const checkboxes = Array.from(document.querySelectorAll('input[name="serviciosInteres"]'));
  checkboxes.forEach((box) => {
    box.addEventListener("change", () => {
      validateServiciosInteres();
      evaluateLowVolumeWarning();
      successMessage.classList.add("hidden");
    });
  });

  const radios = Array.from(document.querySelectorAll('input[name="tresplActual"]'));
  radios.forEach((radio) => {
    radio.addEventListener("change", () => {
      validateTresplActual();
      successMessage.classList.add("hidden");
    });
  });
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const valid = validateAll();
  if (!valid) {
    successMessage.classList.add("hidden");
    return;
  }

  successMessage.classList.remove("hidden");
  form.reset();
  comentariosCounter.textContent = "500 caracteres restantes";
  volumeWarning.classList.add("hidden");

  trackedFields.forEach((id) => {
    const el = getField(id);
    if (!el) return;
    el.classList.remove("border-rose-500", "focus:border-rose-500", "focus:ring-rose-200");
    el.classList.remove("border-emerald-500", "focus:border-emerald-500", "focus:ring-emerald-200");
    el.setAttribute("aria-invalid", "false");
  });

  [
    "nombreEmpresa",
    "personaContacto",
    "emailCorporativo",
    "telefono",
    "sitioWeb",
    "paisOperacion",
    "tipoProducto",
    "volumenMensual",
    "serviciosInteres",
    "tresplActual",
    "comentarios",
    "aceptoPrivacidad",
  ].forEach((id) => setError(id, ""));
});

form.addEventListener("reset", () => {
  successMessage.classList.add("hidden");
  volumeWarning.classList.add("hidden");
  comentariosCounter.textContent = "500 caracteres restantes";

  [
    "nombreEmpresa",
    "personaContacto",
    "emailCorporativo",
    "telefono",
    "sitioWeb",
    "paisOperacion",
    "tipoProducto",
    "volumenMensual",
    "serviciosInteres",
    "tresplActual",
    "comentarios",
    "aceptoPrivacidad",
  ].forEach((id) => setError(id, ""));
});

if (comentarios) {
  comentariosCounter.textContent = "500 caracteres restantes";
}

bindValidation();
