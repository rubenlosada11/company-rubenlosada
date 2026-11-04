import { deferredModule } from "./deferredModule";

type Tracked = Promise<string> & { status?: string; value?: string; reason?: unknown };

describe("deferredModule", () => {
  it("descarga el módulo una sola vez aunque se pida varias veces", async () => {
    const load = jest.fn(() => Promise.resolve("Formulario"));
    const get = deferredModule(load);

    expect(get()).toBe(get());
    await expect(get()).resolves.toBe("Formulario");
    expect(load).toHaveBeenCalledTimes(1);
  });

  it("marca la promesa con status y value al resolverse (use() la lee sin suspender)", async () => {
    const get = deferredModule(() => Promise.resolve("Formulario"));
    const promise = get() as Tracked;

    expect(promise.status).toBe("pending");
    await promise;
    expect(promise.status).toBe("fulfilled");
    expect(promise.value).toBe("Formulario");
  });

  it("tras un fallo de descarga, el siguiente intento vuelve a pedir el módulo", async () => {
    const error = new Error("ChunkLoadError");
    const load = jest.fn().mockRejectedValueOnce(error).mockResolvedValueOnce("Formulario");
    const get = deferredModule<string>(load);

    const failed = get() as Tracked;
    await expect(failed).rejects.toBe(error);
    expect(failed.status).toBe("rejected");
    expect(failed.reason).toBe(error);

    await expect(get()).resolves.toBe("Formulario");
    expect(load).toHaveBeenCalledTimes(2);
  });
});
