"use client";

import { useState, type FormEvent } from "react";
import { EmptyState, ErrorBanner, InlineError, LoadingBlock } from "@/components/StateBanner";
import { formatDateTime } from "@/lib/domain";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { useNotes } from "@/hooks/useNotes";
import { recordsService } from "@/services/records";

export function NotesPanel({
  recordId,
  onNotesCountChange,
}: {
  recordId: string;
  onNotesCountChange: (count: number) => void;
}) {
  const [retryKey, setRetryKey] = useState(0);

  return (
    <section className="space-y-4 rounded-3xl border border-slate-200 bg-white p-6 shadow-lg shadow-slate-900/5">
      <h2 className="font-heading text-lg font-bold text-slate-900">Notas</h2>
      <NotesPanelContent
        key={`${recordId}-${retryKey}`}
        recordId={recordId}
        onNotesCountChange={onNotesCountChange}
        onRetry={() => setRetryKey((k) => k + 1)}
      />
    </section>
  );
}

function NotesPanelContent({
  recordId,
  onNotesCountChange,
  onRetry,
}: {
  recordId: string;
  onNotesCountChange: (count: number) => void;
  onRetry: () => void;
}) {
  const { state, addNoteLocally, removeNoteLocally } = useNotes(recordId);
  const [content, setContent] = useState("");
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const addAction = useAsyncAction((text: string) => recordsService.addNote(recordId, { content: text }));
  const deleteAction = useAsyncAction((noteId: string) => recordsService.deleteNote(recordId, noteId));

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmed = content.trim();
    if (!trimmed) return;

    const result = await addAction.run(trimmed);
    if (result.ok) {
      addNoteLocally(result.data);
      setContent("");
      if (state.status === "success") onNotesCountChange(state.data.length + 1);
    }
  }

  async function handleDelete(noteId: string) {
    setDeletingId(noteId);
    const result = await deleteAction.run(noteId);
    setDeletingId(null);
    if (!result.ok) return;
    removeNoteLocally(noteId);
    if (state.status === "success") onNotesCountChange(Math.max(0, state.data.length - 1));
  }

  return (
    <>
      <form onSubmit={handleSubmit} className="space-y-2">
        <label htmlFor="note-content" className="text-sm font-semibold text-slate-700">
          Añadir una nota
        </label>
        <textarea
          id="note-content"
          value={content}
          onChange={(e) => setContent(e.target.value)}
          disabled={addAction.isLoading}
          rows={3}
          className="w-full rounded-xl border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 shadow-sm transition focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
          placeholder="Comentario sobre esta candidatura…"
        />
        {addAction.error && <InlineError message={addAction.error} />}
        <button
          type="submit"
          disabled={addAction.isLoading || !content.trim()}
          className="rounded-full bg-blue-700 px-4 py-2 text-sm font-bold text-white shadow-md shadow-blue-900/20 transition hover:-translate-y-0.5 hover:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:translate-y-0"
        >
          {addAction.isLoading ? "Añadiendo…" : "Añadir nota"}
        </button>
      </form>

      {state.status === "loading" && <LoadingBlock label="Cargando notas…" />}
      {state.status === "error" && <ErrorBanner message={state.message} onRetry={onRetry} />}
      {state.status === "success" && state.data.length === 0 && (
        <EmptyState title="Sin notas todavía" description="Añade la primera nota sobre esta candidatura." />
      )}

      {state.status === "success" && state.data.length > 0 && (
        <ul className="space-y-3">
          {state.data.map((note) => (
            <li key={note.id} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <div className="flex items-start justify-between gap-3">
                <p className="whitespace-pre-wrap text-sm text-slate-800">{note.content}</p>
                <button
                  type="button"
                  onClick={() => handleDelete(note.id)}
                  disabled={deletingId === note.id}
                  className="shrink-0 rounded-full border border-slate-300 bg-white px-2.5 py-1 text-xs font-bold text-slate-600 transition hover:border-rose-300 hover:text-rose-700 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {deletingId === note.id ? "Eliminando…" : "Eliminar"}
                </button>
              </div>
              <p className="mt-2 text-xs font-semibold text-slate-500">{formatDateTime(note.created_at)}</p>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
