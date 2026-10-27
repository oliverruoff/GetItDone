// A small adapter for pi's public extension events. No prompt or credentials are stored.
import { writeFileSync, renameSync } from "node:fs";
export default function (pi: any) {
  const target = process.env.GETITDONE_PI_STATUS;
  if (!target) return;
  let message: string | null = null;
  const publish = (state: string) => {
    const temp = target + ".tmp";
    writeFileSync(temp, JSON.stringify({state, message, source: "pi extension events"}));
    renameSync(temp, target);
  };
  pi.on("session_start", async () => publish("Ready"));
  pi.on("agent_start", async () => publish("Working"));
  pi.on("agent_end", async (event: any) => {
    const last = [...(event.messages ?? [])].reverse().find((m: any) => m.role === "assistant");
    message = new Date().toISOString();
    publish(last?.stopReason === "error" ? "Failed" : last?.stopReason === "aborted" ? "Interrupted" : "Ready");
  });
}
