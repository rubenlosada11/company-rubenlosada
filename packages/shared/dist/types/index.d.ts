/**
 * Shared types for transversal project apps.
 */
export type Id = string;
export interface BaseEntity {
    id: Id;
    createdAt?: string;
    updatedAt?: string;
}
export * from "./models.js";
