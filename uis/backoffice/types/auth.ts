/** Tipos de autenticación de `services/api` (`/auth`). */
export type UserRole = "admin" | "manager" | "user";

export interface Profile {
  id: string;
  user_id: string;
  name: string | null;
  phone: string | null;
  address: string | null;
}

/** Respuesta de `GET /auth/me`. Nunca incluye el hash de la contraseña. */
export interface CurrentUser {
  id: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  profile: Profile;
}

export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
  /** Segundos de validez del token. */
  expires_in: number;
}
