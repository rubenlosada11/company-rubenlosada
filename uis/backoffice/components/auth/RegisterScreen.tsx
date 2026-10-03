"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { AccountCreatedError } from "@/lib/auth";
import { toFormErrors } from "@/lib/authErrors";
import { EMAIL_PATTERN, PASSWORD_MIN_LENGTH, passwordProblem } from "@/lib/authRules";
import { ApiError } from "@/lib/http";
import type { RegisterPayload } from "@/types/auth";
import { Spinner } from "./AuthGate";
import { useAuth } from "./AuthProvider";
import {
  AlertIcon,
  ArrowIcon,
  AuthShell,
  FieldError,
  iconClasses,
  InfoIcon,
  inputClasses,
  KeyIcon,
  MailIcon,
  PasswordInput,
  PhoneIcon,
  PinIcon,
  UserIcon,
} from "./AuthShell";

interface RegisterScreenProps {
  /** Ruta interna a la que ir tras crear la cuenta (ya saneada por la página). */
  next: string;
}

type FieldName = "email" | "password" | "name" | "phone" | "address" | "invitation_code";
type Values = Record<FieldName, string>;

const FIELDS: readonly FieldName[] = ["email", "password", "name", "phone", "address", "invitation_code"];
const EMPTY: Values = { email: "", password: "", name: "", phone: "", address: "", invitation_code: "" };

/** Errores que se detectan sin llamar a la API: obligatorios, formato del email y longitud de la contraseña. */
function validate(values: Values): Partial<Record<FieldName, string>> {
  const errors: Partial<Record<FieldName, string>> = {};
  const email = values.email.trim();
  if (!email) errors.email = "Escribe tu email.";
  else if (!EMAIL_PATTERN.test(email)) errors.email = "El email no tiene un formato válido.";
  if (!values.password) errors.password = "Elige una contraseña.";
  else {
    const problem = passwordProblem(values.password);
    if (problem) errors.password = problem;
  }
  return errors;
}

/** Cuerpo de `POST /users`: los opcionales vacíos no se envían. */
function toPayload(values: Values): RegisterPayload {
  const payload: RegisterPayload = { email: values.email.trim(), password: values.password };
  for (const field of ["name", "phone", "address", "invitation_code"] as const) {
    const value = values[field].trim();
    if (value) payload[field] = value;
  }
  return payload;
}

export function RegisterScreen({ next }: RegisterScreenProps) {
  const { status, register } = useAuth();
  const router = useRouter();
  const [values, setValues] = useState<Values>(EMPTY);
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<FieldName, string>>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [emailTaken, setEmailTaken] = useState(false);
  const [accountCreated, setAccountCreated] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);
  /** Campo a enfocar tras el próximo render (durante el envío los inputs están deshabilitados y no aceptan foco). */
  const pendingFocus = useRef<FieldName | null>(null);

  const loginHref = next === "/" ? "/login" : `/login?${new URLSearchParams({ next })}`;

  // Tras el alta y el login automático (o con una sesión ya abierta), al panel.
  useEffect(() => {
    if (status === "authenticated") router.replace(next);
  }, [status, next, router]);

  useEffect(() => {
    if (submitting || !pendingFocus.current) return;
    formRef.current?.querySelector<HTMLInputElement>(`#register-${pendingFocus.current}`)?.focus();
    pendingFocus.current = null;
  });

  function update(field: FieldName, value: string) {
    setValues((current) => ({ ...current, [field]: value }));
    // El error de un campo desaparece al corregirlo.
    setFieldErrors((current) => {
      const rest = { ...current };
      delete rest[field];
      return rest;
    });
    if (field === "email") setEmailTaken(false);
  }

  function focusFirstError(errors: Partial<Record<FieldName, string>>) {
    pendingFocus.current = FIELDS.find((field) => errors[field]) ?? null;
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    setEmailTaken(false);

    const clientErrors = validate(values);
    if (Object.keys(clientErrors).length > 0) {
      setFieldErrors(clientErrors);
      setFormError("Revisa los campos marcados.");
      focusFirstError(clientErrors);
      return;
    }

    setFieldErrors({});
    setSubmitting(true);
    try {
      await register(toPayload(values));
      // La redirección la hace el efecto de arriba al pasar a `authenticated`.
    } catch (caught) {
      setSubmitting(false);
      if (caught instanceof AccountCreatedError) {
        setAccountCreated(true);
        return;
      }
      if (caught instanceof ApiError && caught.status === 409) {
        const errors = { email: "Este email ya está registrado." };
        setFieldErrors(errors);
        setFormError("No se ha creado la cuenta: ya existe una cuenta con ese email.");
        setEmailTaken(true);
        focusFirstError(errors);
        return;
      }
      if (caught instanceof ApiError && caught.status === 403) {
        const errors = { invitation_code: "El código de invitación no es válido. Pídeselo a un administrador." };
        setFieldErrors(errors);
        setFormError("No se ha creado la cuenta: hace falta un código de invitación válido.");
        focusFirstError(errors);
        return;
      }
      const { fields, message } = toFormErrors(caught, FIELDS);
      setFieldErrors(fields);
      setFormError(message);
      focusFirstError(fields);
    }
  }

  const busy = submitting || status === "authenticated";

  if (accountCreated) {
    return (
      <AuthShell footnote="La sesión se guarda en este navegador y caduca automáticamente.">
        <p className="text-xs font-bold tracking-[0.17em] text-blue-800 uppercase">Cuenta creada</p>
        <h1 className="mt-3 font-heading text-3xl leading-tight tracking-tight text-slate-900">Ya casi está</h1>
        <p
          role="status"
          className="mt-6 flex items-start gap-2.5 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"
        >
          <InfoIcon className="mt-0.5 size-4 shrink-0" />
          Tu cuenta se ha creado, pero no se pudo iniciar sesión automáticamente. Inicia sesión con tu email y tu
          contraseña para continuar.
        </p>
        <Link
          href={loginHref}
          className="mt-6 flex w-full items-center justify-center gap-2 rounded-full bg-blue-700 px-5 py-3.5 font-bold text-white transition hover:bg-blue-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700"
        >
          Ir a iniciar sesión
          <ArrowIcon className="size-4" />
        </Link>
      </AuthShell>
    );
  }

  return (
    <AuthShell footnote="La sesión se guarda en este navegador y caduca automáticamente.">
      <p className="text-xs font-bold tracking-[0.17em] text-blue-800 uppercase">Acceso del equipo</p>
      <h1 className="mt-3 font-heading text-3xl leading-tight tracking-tight text-slate-900">Crea tu cuenta</h1>
      <p className="mt-2 text-slate-600">Regístrate para usar el panel interno de TrackFlow.</p>

      {formError && (
        <div
          role="alert"
          className="mt-6 flex items-start gap-2.5 rounded-xl border border-red-200 bg-red-50 p-3 text-sm font-semibold text-red-800"
        >
          <AlertIcon className="mt-0.5 size-4 shrink-0" />
          <p>{formError}</p>
        </div>
      )}

      <form ref={formRef} onSubmit={handleSubmit} noValidate className="mt-7 space-y-5">
        <Field
          id="email"
          label="Email"
          required
          icon={<MailIcon className={iconClasses} />}
          error={fieldErrors.email}
          extra={
            emailTaken ? (
              <Link href={loginHref} className="font-bold text-blue-700 underline-offset-2 hover:underline">
                ¿Es tuya? Inicia sesión
              </Link>
            ) : null
          }
        >
          {(props) => (
            <input
              {...props}
              type="email"
              inputMode="email"
              autoComplete="email"
              autoFocus
              placeholder="nombre@trackflow.com"
              value={values.email}
              onChange={(event) => update("email", event.target.value)}
              disabled={busy}
              className={`${inputClasses} pr-4`}
            />
          )}
        </Field>

        <div className="space-y-1.5">
          <label htmlFor="register-password" className="text-sm font-bold text-slate-700">
            Contraseña <span className="text-red-700" aria-hidden="true">*</span>
          </label>
          <PasswordInput
            id="register-password"
            autoComplete="new-password"
            value={values.password}
            onChange={(value) => update("password", value)}
            disabled={busy}
            invalid={Boolean(fieldErrors.password)}
            describedBy={fieldErrors.password ? "register-password-hint register-password-error" : "register-password-hint"}
          />
          <p id="register-password-hint" className="text-xs text-slate-500">
            Mínimo {PASSWORD_MIN_LENGTH} caracteres.
          </p>
          <FieldError id="register-password-error" message={fieldErrors.password} />
        </div>

        {/* Grupo con `role="group"` en lugar de <fieldset>/<legend>: la leyenda sobre el borde dejaba un hueco grande. */}
        <div role="group" aria-labelledby="register-contact" className="space-y-5 border-t border-slate-100 pt-5">
          <p id="register-contact" className="text-sm font-bold text-slate-900">
            Datos de contacto <span className="font-semibold text-slate-500">(opcionales)</span>
          </p>
          <Field id="name" label="Nombre" icon={<UserIcon className={iconClasses} />} error={fieldErrors.name}>
            {(props) => (
              <input
                {...props}
                type="text"
                autoComplete="name"
                maxLength={100}
                placeholder="Nombre y apellidos"
                value={values.name}
                onChange={(event) => update("name", event.target.value)}
                disabled={busy}
                className={`${inputClasses} pr-4`}
              />
            )}
          </Field>
          <Field id="phone" label="Teléfono" icon={<PhoneIcon className={iconClasses} />} error={fieldErrors.phone}>
            {(props) => (
              <input
                {...props}
                type="tel"
                inputMode="tel"
                autoComplete="tel"
                maxLength={25}
                placeholder="+34 976 000 000"
                value={values.phone}
                onChange={(event) => update("phone", event.target.value)}
                disabled={busy}
                className={`${inputClasses} pr-4`}
              />
            )}
          </Field>
          <Field id="address" label="Dirección" icon={<PinIcon className={iconClasses} />} error={fieldErrors.address}>
            {(props) => (
              <input
                {...props}
                type="text"
                autoComplete="street-address"
                maxLength={200}
                placeholder="Calle, ciudad"
                value={values.address}
                onChange={(event) => update("address", event.target.value)}
                disabled={busy}
                className={`${inputClasses} pr-4`}
              />
            )}
          </Field>
        </div>

        <Field
          id="invitation_code"
          label="Código de invitación"
          hint="Te lo facilita un administrador de TrackFlow. Es obligatorio si el registro está restringido."
          icon={<KeyIcon className={iconClasses} />}
          error={fieldErrors.invitation_code}
        >
          {(props) => (
            <input
              {...props}
              type="text"
              autoComplete="off"
              autoCapitalize="none"
              spellCheck={false}
              maxLength={200}
              value={values.invitation_code}
              onChange={(event) => update("invitation_code", event.target.value)}
              disabled={busy}
              className={`${inputClasses} pr-4`}
            />
          )}
        </Field>

        <button
          type="submit"
          disabled={busy}
          className="group flex w-full items-center justify-center gap-2 rounded-full bg-blue-700 px-5 py-3.5 font-bold text-white shadow-lg shadow-blue-700/25 transition hover:bg-blue-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700 disabled:cursor-wait disabled:bg-blue-700/80"
        >
          {busy ? (
            <>
              <Spinner className="size-5" />
              Creando tu cuenta…
            </>
          ) : (
            <>
              Crear cuenta
              <ArrowIcon className="size-4 transition group-hover:translate-x-0.5 motion-reduce:transition-none" />
            </>
          )}
        </button>
      </form>

      <p className="mt-6 border-t border-slate-100 pt-5 text-sm text-slate-500">
        ¿Ya tienes cuenta?{" "}
        <Link href={loginHref} className="font-bold text-blue-700 underline-offset-2 hover:underline">
          Inicia sesión
        </Link>
      </p>
    </AuthShell>
  );
}

interface FieldProps {
  id: FieldName;
  label: string;
  required?: boolean;
  hint?: string;
  icon: React.ReactNode;
  error?: string;
  /** Contenido bajo el error (p. ej. el enlace al login si el email ya existe). */
  extra?: React.ReactNode;
  children: (props: {
    id: string;
    name: string;
    required?: boolean;
    "aria-invalid"?: true;
    "aria-describedby"?: string;
  }) => React.ReactNode;
}

function Field({ id, label, required, hint, icon, error, extra, children }: FieldProps) {
  const inputId = `register-${id}`;
  const describedBy = [hint && `${inputId}-hint`, error && `${inputId}-error`].filter(Boolean).join(" ") || undefined;
  return (
    <div className="space-y-1.5">
      <label htmlFor={inputId} className="text-sm font-bold text-slate-700">
        {label} {required && <span className="text-red-700" aria-hidden="true">*</span>}
      </label>
      <div className="relative">
        {children({
          id: inputId,
          name: id,
          required,
          "aria-invalid": error ? true : undefined,
          "aria-describedby": describedBy,
        })}
        {icon}
      </div>
      {hint && (
        <p id={`${inputId}-hint`} className="text-xs text-slate-500">
          {hint}
        </p>
      )}
      <FieldError id={`${inputId}-error`} message={error} />
      {extra && <p className="text-sm">{extra}</p>}
    </div>
  );
}
