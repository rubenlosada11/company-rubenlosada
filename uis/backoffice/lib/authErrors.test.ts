/**
 * AUTH-088 — errores de la API en los formularios de cuenta (`lib/authErrors.ts`). Ver TESTING.md §9.
 *
 * Los mensajes de entrada son los que redacta `services/api` (comprobados contra `app/dependencies.py` y
 * `app/auth_models.py`).
 */
import { toFormErrors, translateApiMessage } from "@/lib/authErrors";
import { ApiError, FORM_ERROR, SERVER_ERROR_MESSAGE, SESSION_EXPIRED_MESSAGE } from "@/lib/http";

describe("translateApiMessage", () => {
  it.each([
    "Token no válido.",
    "El token ha caducado. Inicia sesión de nuevo.",
    "No autenticado. Inicia sesión y envía el token en la cabecera Authorization: Bearer <token>.",
  ])("convierte el 401 técnico «%s» en el aviso de sesión caducada", (message) => {
    expect(translateApiMessage(message)).toBe(SESSION_EXPIRED_MESSAGE);
  });

  it("pule un mensaje conocido con el nombre técnico del campo", () => {
    expect(translateApiMessage("email no tiene un formato válido")).toBe("El email no tiene un formato válido.");
  });

  it("deja igual un mensaje desconocido y le añade el punto final si falta", () => {
    expect(translateApiMessage("  Ya existe un usuario con ese email.  ")).toBe("Ya existe un usuario con ese email.");
    expect(translateApiMessage("Código de invitación no válido")).toBe("Código de invitación no válido.");
  });
});

describe("toFormErrors", () => {
  it("reparte los errores entre los campos visibles y el mensaje general", () => {
    const error = new ApiError("Revisa los datos y vuelve a intentarlo.", 422, {
      email: "email no tiene un formato válido",
      phone: "phone no tiene un formato de teléfono válido",
      [FORM_ERROR]: "La nueva contraseña debe ser distinta de la actual",
    });

    const result = toFormErrors(error, ["email", "password"]);

    expect(result.fields).toEqual({ email: "El email no tiene un formato válido." });
    // El campo no visible no se pierde: va al mensaje general con su etiqueta.
    expect(result.message).toBe(
      "Teléfono: El teléfono no tiene un formato válido (p. ej. +34 976 000 000). " +
        "La nueva contraseña debe ser distinta de la actual.",
    );
  });

  it("con todos los errores en campos visibles, el aviso general solo pide revisarlos", () => {
    const error = new ApiError("x", 422, { password: "La contraseña debe tener al menos 8 caracteres" });
    expect(toFormErrors(error, ["password"])).toEqual({
      fields: { password: "La contraseña debe tener al menos 8 caracteres." },
      message: "Revisa los campos marcados.",
    });
  });

  it("un campo sin etiqueta conocida usa su nombre", () => {
    expect(toFormErrors(new ApiError("x", 422, { extra: "No admitido" }), []).message).toBe("extra: No admitido.");
  });

  it("un error sin campos muestra el mensaje de la API pulido", () => {
    expect(toFormErrors(new ApiError("Token no válido.", 401), ["email"])).toEqual({
      fields: {},
      message: SESSION_EXPIRED_MESSAGE,
    });
  });

  it.each([500, 503])("un %i nunca muestra el detalle del servidor", (status) => {
    const result = toFormErrors(new ApiError("Traceback: KeyError 'users'", status), ["email"]);
    expect(result).toEqual({ fields: {}, message: SERVER_ERROR_MESSAGE });
  });

  it("un error que no viene de la API no muestra su mensaje técnico", () => {
    const result = toFormErrors(new TypeError("Cannot read properties of undefined"), ["email"]);
    expect(result).toEqual({ fields: {}, message: "Error inesperado. Inténtalo de nuevo." });
  });
});
