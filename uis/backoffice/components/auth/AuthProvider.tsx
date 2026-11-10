"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { AccountCreatedError, authApi } from "@/lib/auth";
import { ApiError, apiErrorMessage } from "@/lib/http";
import { clearToken, readToken, saveToken, TOKEN_KEY, tokenExpiry, UNAUTHORIZED_EVENT } from "@/lib/session";
import { track } from "@/lib/telemetry";
import type { FrontendEventProperties } from "@/lib/telemetryCatalog";
import {
  beginTelemetrySession,
  clearTelemetrySession,
  commitTelemetrySession,
  currentTelemetrySession,
  discardPendingTelemetrySession,
  ensureTelemetrySession,
} from "@/lib/telemetrySession";
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
  /**
   * `POST /auth/change-password` y guarda el token nuevo que devuelve la API (las sesiones anteriores, también la de
   * este navegador, dejan de valer). Un 400 (contraseña actual incorrecta) o 422 llegan como `ApiError`.
   */
  changePassword: (currentPassword: string, newPassword: string) => Promise<void>;
  retry: () => void;
}

const STORAGE_BLOCKED_MESSAGE =
  "Tu navegador no permite guardar la sesión. Sal del modo privado o permite el almacenamiento de este sitio e inténtalo de nuevo.";

const AuthContext = createContext<AuthContextValue | null>(null);

type SessionEndReason = FrontendEventProperties["session_ended"]["end_reason"];

/** Máximo de `session_duration_seconds` en el contrato (30 días). */
const MAX_SESSION_SECONDS = 2_592_000;

/**
 * Telemetría del fin de la sesión: `session_ended` y borrado del `sessionId`. Una sola vez por sesión: si otra pestaña
 * ya la cerró (y borró el `sessionId` compartido), esta no repite el evento.
 */
function reportSessionEnd(reason: SessionEndReason): void {
  const session = currentTelemetrySession();
  if (!session) return;
  const seconds = Math.round((Date.now() - session.startedAt) / 1000);
  track("session_ended", {
    end_reason: reason,
    session_duration_seconds: Math.min(Math.max(seconds, 0), MAX_SESSION_SECONDS),
  });
  clearTelemetrySession();
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [endReason, setEndReason] = useState<EndReason>(null);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  /** Cambia cuando se guarda un token nuevo sin pasar por el login (cambio de contraseña): reprograma la caducidad. */
  const [tokenVersion, setTokenVersion] = useState(0);

  // `telemetryReason` distingue para la telemetría lo que la interfaz trata igual (caducidad, 401, otra pestaña).
  const endSession = useCallback((reason: Exclude<EndReason, null>, telemetryReason: SessionEndReason) => {
    reportSessionEnd(telemetryReason);
    clearToken();
    setUser(null);
    setEndReason(reason);
    setStatus("anonymous");
  }, []);

  const logout = useCallback(
    (reason: Exclude<EndReason, null> = "logout") =>
      endSession(reason, reason === "logout" ? "user_logout" : "token_expired"),
    [endSession]
  );

  // Al cargar (y al reintentar): valida el token guardado en este navegador. `localStorage` solo se lee aquí, en un
  // efecto (nunca en el render del servidor), así que el primer render es igual en servidor y cliente: `loading`.
  useEffect(() => {
    const controller = new AbortController();

    async function restore() {
      const token = readToken();
      const expiry = token ? tokenExpiry(token) : null;
      if (!token || (expiry !== null && expiry <= Date.now())) {
        if (token) {
          reportSessionEnd("token_expired");
          clearToken();
        }
        setUser(null);
        setEndReason(token ? "expired" : null);
        setStatus("anonymous");
        return;
      }
      try {
        const me = await authApi.me(controller.signal);
        // Sesión guardada sin `sessionId` (anterior a la telemetría): se crea ahora.
        ensureTelemetrySession();
        setUser(me);
        setStatus("authenticated");
      } catch (error) {
        if (controller.signal.aborted) return;
        if (error instanceof ApiError && error.status === 401) {
          reportSessionEnd("unauthorized_response");
          setUser(null);
          setEndReason("expired");
          setStatus("anonymous");
        } else {
          setConnectionError(apiErrorMessage(error, "comprobar tu sesión"));
          setStatus("unreachable");
        }
      }
    }

    void restore();
    return () => controller.abort();
  }, [attempt]);

  // Cualquier 401 de una petición protegida (token caducado, ausente, o usuario desactivado o borrado) cierra la sesión.
  useEffect(() => {
    const onUnauthorized = () => endSession("expired", "unauthorized_response");
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, [endSession]);

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
        // La pestaña que cerró la sesión ya emitió `session_ended`; si no lo hizo, lo emite esta.
        endSession(previous !== null && previous <= Date.now() ? "expired" : "logout", "ended_in_other_tab");
      }
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, [endSession]);

  // Cierre automático cuando caduca el token, aunque no se haga ninguna petición.
  useEffect(() => {
    if (status !== "authenticated") return;
    const token = readToken();
    const expiry = token ? tokenExpiry(token) : null;
    if (expiry === null) return;
    const timer = window.setTimeout(() => logout("expired"), Math.max(expiry - Date.now(), 0));
    return () => window.clearTimeout(timer);
  }, [status, logout, tokenVersion]);

  // El login es público (`auth: false`): no hace falta borrar antes el token, y no hacerlo evita que las demás pestañas
  // vean un cierre de sesión momentáneo. El token solo se guarda si la API lo emite.
  // Telemetría: el `sessionId` nace aquí, antes de enviar el login (viaja en su cabecera `X-Session-Id`), y solo se
  // confirma si hay sesión de verdad.
  const login = useCallback(async (email: string, password: string) => {
    beginTelemetrySession();
    let accessToken: string;
    try {
      accessToken = (await authApi.login(email, password)).access_token;
    } catch (error) {
      discardPendingTelemetrySession();
      throw error;
    }
    // Sin el token guardado, la siguiente petición iría sin autenticar: se avisa aquí con un mensaje que lo explica.
    if (!saveToken(accessToken)) {
      discardPendingTelemetrySession();
      throw new ApiError(STORAGE_BLOCKED_MESSAGE, 0);
    }
    commitTelemetrySession();
    try {
      const me = await authApi.me();
      setUser(me);
      setEndReason(null);
      setConnectionError(null);
      setStatus("authenticated");
    } catch (error) {
      clearToken();
      clearTelemetrySession();
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

  // El usuario no cambia: solo el token. Las demás pestañas reciben el evento `storage` y revalidan con el token nuevo.
  const changePassword = useCallback(async (currentPassword: string, newPassword: string) => {
    const { access_token } = await authApi.changePassword(currentPassword, newPassword);
    saveToken(access_token);
    setTokenVersion((n) => n + 1);
  }, []);

  const setProfile = useCallback((profile: Profile) => {
    setUser((current) => (current ? { ...current, profile } : current));
  }, []);

  const retry = useCallback(() => {
    setStatus("loading");
    setConnectionError(null);
    setAttempt((n) => n + 1);
  }, []);

  const value = useMemo(
    () => ({ status, user, endReason, connectionError, login, register, logout, setProfile, changePassword, retry }),
    [status, user, endReason, connectionError, login, register, logout, setProfile, changePassword, retry]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth debe usarse dentro de <AuthProvider>.");
  return context;
}
