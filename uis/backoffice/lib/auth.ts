import { http } from "@/lib/http";
import type {
  CurrentUser,
  MessageResponse,
  Profile,
  ProfileUpdate,
  RegisterPayload,
  TokenResponse,
  UserRole,
} from "@/types/auth";

/** Página del perfil del usuario conectado (privada, dentro de `app/(panel)/`). */
export const PROFILE_PATH = "/account/profile";
/** Recuperación de contraseña (pública). */
export const FORGOT_PASSWORD_PATH = "/forgot-password";
/** Cambio de contraseña con sesión (privada, dentro de `app/(panel)/`). */
export const CHANGE_PASSWORD_PATH = "/account/change-password";

/**
 * Mensaje que se muestra siempre tras pedir el enlace, exista o no el email (AUTH-03). Es fijo en el frontend: no
 * depende de lo que responda la API, así que la pantalla nunca puede revelar si un email está registrado.
 */
export const FORGOT_PASSWORD_MESSAGE =
  "Si esa dirección está registrada, recibirás un enlace para restablecer tu contraseña.";

/** Endpoints de autenticación de `services/api`. El token viaja solo en los protegidos (ver `lib/http.ts`). */
export const authApi = {
  /** Público: su 401 (credenciales incorrectas) no cierra ninguna sesión. */
  login(email: string, password: string): Promise<TokenResponse> {
    return http.post<TokenResponse>("/auth/login", { email, password }, { auth: false });
  },

  /** Público (`POST /users`): crea el usuario y su perfil. No inicia sesión. */
  register(payload: RegisterPayload): Promise<CurrentUser> {
    return http.post<CurrentUser>("/users", payload, { auth: false });
  },

  me(signal?: AbortSignal): Promise<CurrentUser> {
    return http.get<CurrentUser>("/auth/me", signal);
  },

  updateProfile(changes: ProfileUpdate): Promise<Profile> {
    return http.put<Profile>("/profiles/me", changes);
  },

  /** Público: pide el enlace de recuperación. La API responde siempre 200 con el mismo mensaje. */
  forgotPassword(email: string): Promise<MessageResponse> {
    return http.post<MessageResponse>("/auth/forgot-password", { email }, { auth: false });
  },

  /**
   * Protegido: cambia la contraseña con la actual. Devuelve un token nuevo (la API cierra todas las sesiones
   * anteriores, también la de este token). 400 = contraseña actual incorrecta; un 401 cierra la sesión (lib/http.ts).
   */
  changePassword(currentPassword: string, newPassword: string): Promise<TokenResponse> {
    return http.post<TokenResponse>("/auth/change-password", {
      current_password: currentPassword,
      new_password: newPassword,
    });
  },

  /** Público: fija la contraseña nueva con el token del email. 400 = enlace no válido, caducado o ya usado. */
  resetPassword(token: string, newPassword: string): Promise<MessageResponse> {
    return http.post<MessageResponse>("/auth/reset-password", { token, new_password: newPassword }, { auth: false });
  },
};

/** El alta (`POST /users`) fue bien, pero el login automático posterior falló: la cuenta existe y basta con entrar. */
export class AccountCreatedError extends Error {
  constructor(cause: unknown) {
    super("Tu cuenta se ha creado, pero no se pudo iniciar sesión automáticamente. Inicia sesión para continuar.", {
      cause,
    });
    this.name = "AccountCreatedError";
  }
}

export const ROLE_LABELS: Record<UserRole, string> = {
  admin: "Administrador",
  manager: "Manager",
  user: "Usuario",
};

/** Nombre del perfil o, si no tiene, la parte local del email. */
export function displayName(user: CurrentUser): string {
  return user.profile.name?.trim() || user.email.split("@")[0];
}

/** Iniciales para el avatar: "Laura Gómez" → "LG"; "laura@…" → "LA". */
export function initials(user: CurrentUser): string {
  const words = displayName(user).split(/[\s._-]+/).filter(Boolean);
  const letters = words.length > 1 ? words[0][0] + words[1][0] : displayName(user).slice(0, 2);
  return letters.toLocaleUpperCase("es-ES");
}
