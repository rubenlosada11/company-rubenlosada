"use client";

import { useEffect, useRef, useState } from "react";
import { authApi, ROLE_LABELS } from "@/lib/auth";
import { toFormErrors } from "@/lib/authErrors";
import { ApiError } from "@/lib/http";
import type { CurrentUser, Profile } from "@/types/auth";
import { Spinner } from "./AuthGate";
import { useAuth } from "./AuthProvider";
import { AlertIcon, iconClasses, inputClasses, PhoneIcon, PinIcon, UserIcon } from "./AuthShell";

type FieldName = "name" | "phone" | "address";
type Values = Record<FieldName, string>;

const FIELDS: readonly FieldName[] = ["name", "phone", "address"];

const FIELD_CONFIG: Record<FieldName, { label: string; maxLength: number; placeholder: string; autoComplete: string; type: string }> = {
  name: { label: "Nombre", maxLength: 100, placeholder: "Nombre y apellidos", autoComplete: "name", type: "text" },
  phone: { label: "Teléfono", maxLength: 25, placeholder: "+34 976 000 000", autoComplete: "tel", type: "tel" },
  address: { label: "Dirección", maxLength: 200, placeholder: "Calle, ciudad", autoComplete: "street-address", type: "text" },
};

const ICONS: Record<FieldName, React.ReactNode> = {
  name: <UserIcon className={iconClasses} />,
  phone: <PhoneIcon className={iconClasses} />,
  address: <PinIcon className={iconClasses} />,
};

function toValues(profile: Profile): Values {
  return { name: profile.name ?? "", phone: profile.phone ?? "", address: profile.address ?? "" };
}

function formatDate(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleDateString("es-ES", { dateStyle: "long" });
}

/**
 * `/account/profile`: lee el usuario con `GET /auth/me` y guarda los datos de contacto con `PUT /profiles/me`.
 * Email y rol son de solo lectura (no se cambian por `/profiles/me`). Un 401 lo gestiona `lib/http.ts` (vuelta al login).
 */
export function ProfileEditor() {
  const { setProfile } = useAuth();
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const [saved, setSaved] = useState<Values | null>(null);
  const [values, setValues] = useState<Values>({ name: "", phone: "", address: "" });
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<FieldName, string>>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [saving, setSaving] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);
  /** Campo a enfocar tras el próximo render (mientras se guarda, los inputs están deshabilitados). */
  const pendingFocus = useRef<FieldName | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    authApi
      .me(controller.signal)
      .then((me) => {
        setUser(me);
        setSaved(toValues(me.profile));
        setValues(toValues(me.profile));
        setLoadError(null);
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        // 401: `lib/http.ts` ya ha cerrado la sesión y `AuthGate` lleva al login.
        if (error instanceof ApiError && error.status === 401) return;
        setLoadError(error instanceof ApiError ? error.message : "No se pudo cargar tu perfil.");
      });
    return () => controller.abort();
  }, [reloadKey]);

  useEffect(() => {
    if (saving || !pendingFocus.current) return;
    formRef.current?.querySelector<HTMLInputElement>(`#profile-${pendingFocus.current}`)?.focus();
    pendingFocus.current = null;
  });

  function retry() {
    setLoadError(null);
    setUser(null);
    setReloadKey((n) => n + 1);
  }

  function update(field: FieldName, value: string) {
    setValues((current) => ({ ...current, [field]: value }));
    setFieldErrors((current) => {
      const rest = { ...current };
      delete rest[field];
      return rest;
    });
    setSuccess(false);
    setFormError(null);
  }

  const dirty = saved !== null && FIELDS.some((field) => values[field].trim() !== saved[field]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!dirty) return;
    setSaving(true);
    setFormError(null);
    setFieldErrors({});
    setSuccess(false);
    try {
      // Se envían los tres campos: vacío → `null` (la API borra el dato).
      const profile = await authApi.updateProfile({
        name: values.name.trim() || null,
        phone: values.phone.trim() || null,
        address: values.address.trim() || null,
      });
      setProfile(profile);
      setSaved(toValues(profile));
      setValues(toValues(profile));
      setSuccess(true);
    } catch (error) {
      // 401: sesión cerrada por `lib/http.ts`; no hay nada que mostrar aquí.
      if (error instanceof ApiError && error.status === 401) return;
      const { fields, message } = toFormErrors(error, FIELDS);
      setFieldErrors(fields);
      setFormError(message);
      pendingFocus.current = FIELDS.find((field) => fields[field]) ?? null;
    } finally {
      setSaving(false);
    }
  }

  if (loadError) {
    return (
      <div role="alert" className="rounded-2xl border border-amber-200 bg-white p-6 shadow-sm">
        <h2 className="font-heading text-lg text-slate-900">No se pudo cargar tu perfil</h2>
        <p className="mt-2 text-sm text-slate-600">{loadError}</p>
        <button
          type="button"
          onClick={retry}
          className="mt-4 rounded-full bg-blue-700 px-4 py-2 text-sm font-bold text-white transition hover:bg-blue-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700"
        >
          Reintentar
        </button>
      </div>
    );
  }

  if (!user || !saved) {
    return (
      <p role="status" className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white p-6 text-sm font-semibold text-slate-500 shadow-sm">
        <Spinner className="size-5 text-blue-700" />
        Cargando tu perfil…
      </p>
    );
  }

  return (
    <div className="space-y-6">
      <section aria-labelledby="cuenta-title" className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
        <h2 id="cuenta-title" className="font-heading text-xl tracking-tight text-slate-900">
          Cuenta
        </h2>
        <dl className="mt-5 grid gap-5 sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)]">
          <div className="min-w-0">
            <dt className="text-xs font-bold tracking-wide text-slate-500 uppercase">Email</dt>
            <dd className="mt-1 truncate font-semibold text-slate-900" title={user.email}>
              {user.email}
            </dd>
          </div>
          <div>
            <dt className="text-xs font-bold tracking-wide text-slate-500 uppercase">Rol</dt>
            <dd className="mt-1 font-semibold text-slate-900">{ROLE_LABELS[user.role]}</dd>
          </div>
          <div>
            <dt className="text-xs font-bold tracking-wide text-slate-500 uppercase">Alta</dt>
            <dd className="mt-1 font-semibold text-slate-900">{formatDate(user.created_at)}</dd>
          </div>
        </dl>
        <p className="mt-5 text-sm text-slate-500">El email y el rol no se editan en esta pantalla.</p>
      </section>

      <section aria-labelledby="contacto-title" className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
        <h2 id="contacto-title" className="font-heading text-xl tracking-tight text-slate-900">
          Datos de contacto
        </h2>
        <p className="mt-1.5 text-sm text-slate-600">Opcionales. Deja un campo vacío para borrarlo.</p>

        {formError && (
          <p
            role="alert"
            className="mt-5 flex items-start gap-2.5 rounded-xl border border-red-200 bg-red-50 p-3 text-sm font-semibold text-red-800"
          >
            <AlertIcon className="mt-0.5 size-4 shrink-0" />
            {formError}
          </p>
        )}

        <form ref={formRef} onSubmit={handleSubmit} noValidate className="mt-6 space-y-5">
          {FIELDS.map((field) => {
            const config = FIELD_CONFIG[field];
            const id = `profile-${field}`;
            const error = fieldErrors[field];
            return (
              <div key={field} className="space-y-1.5">
                <label htmlFor={id} className="text-sm font-bold text-slate-700">
                  {config.label}
                </label>
                <div className="relative">
                  <input
                    id={id}
                    name={field}
                    type={config.type}
                    autoComplete={config.autoComplete}
                    maxLength={config.maxLength}
                    placeholder={config.placeholder}
                    value={values[field]}
                    onChange={(event) => update(field, event.target.value)}
                    disabled={saving}
                    aria-invalid={error ? true : undefined}
                    aria-describedby={error ? `${id}-error` : undefined}
                    className={`${inputClasses} pr-4`}
                  />
                  {ICONS[field]}
                </div>
                {error && (
                  <p id={`${id}-error`} className="flex items-start gap-1.5 text-sm font-semibold text-red-700">
                    <AlertIcon className="mt-0.5 size-4 shrink-0" />
                    {error}
                  </p>
                )}
              </div>
            );
          })}

          <div className="flex flex-wrap items-center gap-4 pt-1">
            <button
              type="submit"
              disabled={!dirty || saving}
              className="inline-flex items-center gap-2 rounded-full bg-blue-700 px-5 py-2.5 text-sm font-bold text-white transition hover:bg-blue-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-600"
            >
              {saving ? (
                <>
                  <Spinner className="size-4" />
                  Guardando…
                </>
              ) : (
                "Guardar cambios"
              )}
            </button>
            {dirty && !saving && (
              <button
                type="button"
                onClick={() => {
                  setValues(saved);
                  setFieldErrors({});
                  setFormError(null);
                }}
                className="rounded-full px-3 py-2 text-sm font-bold text-slate-600 transition hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-2 focus-visible:outline-blue-700"
              >
                Descartar cambios
              </button>
            )}
            <p role="status" className="text-sm font-semibold text-emerald-700">
              {success ? "Perfil actualizado." : ""}
            </p>
          </div>
        </form>
      </section>
    </div>
  );
}
