"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { AccountCreatedError, authApi } from "@/lib/auth";
import { ApiError } from "@/lib/http";
import { clearToken, readToken, saveToken, TOKEN_KEY, tokenExpiry, UNAUTHORIZED_EVENT } from "@/lib/session";
import type { CurrentUser, Profile, RegisterPayload } from "@/types/auth";

/**
 * - `loading`: comprobando el token guardado contra `GET /auth/me`.
 * - `anonymous`: sin sesión (nunca inició, cerró sesión o caducó: ver `endReason`).
 * - `unreachable`: hay token, pero la API no responde; no se sabe si sigue siendo válido.
 */
export type AuthStatus = "loading" | "authenticated" | "anonymous" | "unreachable";
export type EndReason = "logout" | "expired" | null;

interface AuthContextValue {
  status: AuthStatus;
  user: CurrentUser | null;
  endReason: EndReason;
  /** Mensaje del error de conexión cuando `status === "unreachable"`. */
  connectionError: string | null;
  login: (email: string, password: string) => Promise<void>;
  /** `POST /users` y, si va bien, login automático. Si solo falla el login lanza `AccountCreatedError`. */
  register: (payload: RegisterPayload) => Promise<void>;
  logout: (reason?: Exclude<EndReason, null>) => void;
  /** Sustituye el perfil del usuario conectado tras `PUT /profiles/me` (sidebar y barra superior al día). */
  setProfile: (profile: Profile) => void;
  retry: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [endReason, setEndReason] = useState<EndReason>(null);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  const logout = useCallback((reason: Exclude<EndReason, null> = "logout") => {
    clearToken();
    setUser(null);
    setEndReason(reason);
    setStatus("anonymous");
  }, []);

  // Al cargar (y al reintentar): valida el token guardado en este navegador. `localStorage` solo se lee aquí, en un
  // efecto (nunca en el render del servidor), así que el primer render es igual en servidor y cliente: `loading`.
  useEffect(() => {
    const controller = new AbortController();

    async function restore() {
      const token = readToken();
      const expiry = token ? tokenExpiry(token) : null;
      if (!token || (expiry !== null && expiry <= Date.now())) {
        if (token) clearToken();
        setUser(null);
        setEndReason(token ? "expired" : null);
        setStatus("anonymous");
        return;
      }
      try {
        const me = await authApi.me(controller.signal);
        setUser(me);
        setStatus("authenticated");
      } catch (error) {
        if (controller.signal.aborted) return;
        if (error instanceof ApiError && error.status === 401) {
          setUser(null);
          setEndReason("expired");
          setStatus("anonymous");
        } else {
          setConnectionError(error instanceof ApiError ? error.message : "No se pudo comprobar la sesión.");
          setStatus("unreachable");
        }
      }
    }

    void restore();
    return () => controller.abort();
  }, [attempt]);

  // Cualquier 401 de una petición protegida (token caducado, ausente, o usuario desactivado o borrado) cierra la sesión.
  useEffect(() => {
    const onUnauthorized = () => logout("expired");
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, [logout]);

  // Sesión compartida entre pestañas (`localStorage`): el navegador avisa a las demás pestañas cuando cambia el token.
  // Si otra pestaña cierra sesión, esta también; si otra inicia sesión, esta revalida el token nuevo con `/auth/me`.
  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.key !== TOKEN_KEY && event.key !== null) return; // `null`: localStorage.clear()
      if (readToken()) {
        setStatus("loading");
        setConnectionError(null);
        setAttempt((n) => n + 1);
      } else {
        const previous = event.oldValue ? tokenExpiry(event.oldValue) : null;
        logout(previous !== null && previous <= Date.now() ? "expired" : "logout");
      }
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, [logout]);

  // Cierre automático cuando caduca el token, aunque no se haga ninguna petición.
  useEffect(() => {
    if (status !== "authenticated") return;
    const token = readToken();
    const expiry = token ? tokenExpiry(token) : null;
    if (expiry === null) return;
    const timer = window.setTimeout(() => logout("expired"), Math.max(expiry - Date.now(), 0));
    return () => window.clearTimeout(timer);
  }, [status, logout]);

  // El login es público (`auth: false`): no hace falta borrar antes el token, y no hacerlo evita que las demás pestañas
  // vean un cierre de sesión momentáneo. El token solo se guarda si la API lo emite.
  const login = useCallback(async (email: string, password: string) => {
    const { access_token } = await authApi.login(email, password);
    saveToken(access_token);
    try {
      const me = await authApi.me();
      setUser(me);
      setEndReason(null);
      setConnectionError(null);
      setStatus("authenticated");
    } catch (error) {
      clearToken();
      throw error;
    }
  }, []);

  const register = useCallback(
    async (payload: RegisterPayload) => {
      await authApi.register(payload);
      try {
        await login(payload.email, payload.password);
      } catch (error) {
        throw new AccountCreatedError(error);
      }
    },
    [login]
  );

  const setProfile = useCallback((profile: Profile) => {
    setUser((current) => (current ? { ...current, profile } : current));
  }, []);

  const retry = useCallback(() => {
    setStatus("loading");
    setConnectionError(null);
    setAttempt((n) => n + 1);
  }, []);

  const value = useMemo(
    () => ({ status, user, endReason, connectionError, login, register, logout, setProfile, retry }),
    [status, user, endReason, connectionError, login, register, logout, setProfile, retry]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth debe usarse dentro de <AuthProvider>.");
  return context;
}
