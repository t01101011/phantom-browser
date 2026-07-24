export interface BulkLifecycleResult {
  succeeded: string[];
  failed: Array<{ id: string; error: string }>;
}

export async function runBulkLifecycle(
  ids: string[],
  action: (id: string) => Promise<unknown>,
): Promise<BulkLifecycleResult> {
  const uniqueIds = Array.from(new Set(ids));
  const items = await Promise.all(
    uniqueIds.map(async (id) => {
      try {
        await action(id);
        return { id, ok: true as const };
      } catch (error) {
        return { id, ok: false as const, error: error instanceof Error ? error.message : String(error) };
      }
    }),
  );
  return {
    succeeded: items.filter((item) => item.ok).map((item) => item.id),
    failed: items.filter((item) => !item.ok).map((item) => ({ id: item.id, error: item.error })),
  };
}
