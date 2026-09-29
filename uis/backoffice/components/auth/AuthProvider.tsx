"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { authApi } from "@/lib/auth";
import { ApiError } from "@/lib/http";
import { clearToken, readToken, saveToken, tokenExpiry, UNAUTHORIZED_EVENT } from "@/lib/session";
import type { CurrentUser } from "@/types/auth";

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
  logout: (reason?: Exclude<EndReason, null>) => void;
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

  // Al cargar (y al reintentar): valida el token guardado en esta pestaña.
  useEffect(() => {
    const controller = new AbortController();

    async function restore() {
      const token = readToken();
      const expiry = token ? tokenExpiry(token) : null;
      if (!token || (expiry !== null && expiry <= Date.now())) {
        if (token) clearToken();
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

  // Cualquier 401 de la API con token (caducado, usuario desactivado o borrado) cierra la sesión.
  useEffect(() => {
    const onUnauthorized = () => logout("expired");
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
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

  const login = useCallback(async (email: string, password: string) => {
    clearToken();
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

  const retry = useCallback(() => {
    setStatus("loading");
    setConnectionError(null);
    setAttempt((n) => n + 1);
  }, []);

  const value = useMemo(
    () => ({ status, user, endReason, connectionError, login, logout, retry }),
    [status, user, endReason, connectionError, login, logout, retry]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth debe usarse dentro de <AuthProvider>.");
  return context;
}
