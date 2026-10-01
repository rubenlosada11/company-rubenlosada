import { http } from "@/lib/http";
import type { CurrentUser, Profile, ProfileUpdate, RegisterPayload, TokenResponse, UserRole } from "@/types/auth";

/** Página del perfil del usuario conectado (privada, dentro de `app/(panel)/`). */
export const PROFILE_PATH = "/account/profile";

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
