"use client";
import { useMemo, useState } from "react";
import Panel from "@/components/Panel";
import { TABS } from "@/components/settings/tabs";
import { useHash } from "@/lib/browser";
import { useSettings, useStatus } from "@/lib/hooks";

function Settings() {
  const { settings, loadError, save } = useSettings();
  const { data: status } = useStatus(30000);
  const tabs = useMemo(() => TABS.filter((t) => t.show(status)), [status]);
  const hash = useHash();
  const [picked, setPicked] = useState<string | null>(null);
  const current = tabs.find((t) => t.id === (picked ?? hash)) ?? tabs[0];

  return (
    <Panel title="Settings" sub="every change applies at once and is logged in History">
      <div className="tabs" role="tablist" aria-label="Settings sections">
        {tabs.map((t) => (
          <button
            key={t.id}
            role="tab"
            id={`tab-${t.id}`}
            aria-selected={current?.id === t.id}
            aria-controls="tab-panel"
            className="tab"
            onClick={() => {
              setPicked(t.id);
              history.replaceState(null, "", `#${t.id}`);
            }}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div id="tab-panel" role="tabpanel" aria-labelledby={current ? `tab-${current.id}` : undefined}>
        {loadError ? <p className="msg bad" role="alert">{loadError}</p> : null}
        {settings && current ? current.render({ settings, save, status }) : <div className="empty">Loading…</div>}
      </div>
    </Panel>
  );
}

export default function Page() {
  return <Settings />;
}
