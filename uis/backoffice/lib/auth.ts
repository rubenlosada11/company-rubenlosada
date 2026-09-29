import { http } from "@/lib/http";
import type { CurrentUser, TokenResponse, UserRole } from "@/types/auth";

/** Endpoints de autenticación de `services/api`. */
export const authApi = {
  login(email: string, password: string): Promise<TokenResponse> {
    return http.post<TokenResponse>("/auth/login", { email, password });
  },

  me(signal?: AbortSignal): Promise<CurrentUser> {
    return http.get<CurrentUser>("/auth/me", signal);
  },
};

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
