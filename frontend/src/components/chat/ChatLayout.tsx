import React, { useMemo, useState } from "react";
import {
  ThreadPrimitive,
  ComposerPrimitive,
  MessagePrimitive,
  MessagePartPrimitive,
  useAssistantState,
} from "@assistant-ui/react";
import type { AppSettings } from "../../contexts/ThemeContext";
import { IconGlyph, IconId } from "../admin/IconPicker";
import { LoginBox } from "../LoginBox";
import { CostPanel } from "../CostPanel";
import { AdminPanel } from "../AdminPanel";
import { CitationPanel, Citation } from "../CitationPanel";
import { WelcomeCard } from "./WelcomeCard";
import { AssistantMessageContent } from "./AssistantMessageContent";
import { ChatToolbar } from "./ChatToolbar";
import { ComposerAttachments } from "./ComposerAttachments";
import { useStoreContext } from "../../contexts/StoreContext";
import { useChatContext } from "../../contexts/ChatContext";
import { CreateStoreDialog } from "../CreateStoreDialog";
import { buildAcceptValue, getUploadLimits } from "../../utils/uploadLimits";
import { toast } from "sonner";

const messageCitations = (
  citationByMessage: Record<string, Record<string, Citation[]>>,
  conversationId: string,
  messageId: string,
) => (conversationId ? citationByMessage[conversationId]?.[messageId] ?? [] : []);

type ChatLayoutProps = {
  settings: AppSettings;
  onOpenCustomizer: () => void;
};

export const ChatLayout: React.FC<ChatLayoutProps> = ({ settings, onOpenCustomizer }) => {
  const {
    token,
    setToken,
    stores,
    storeId,
    setStoreId,
    documents,
    refreshStores,
    fetchDocuments,
    pendingUploads,
    handleFiles,
    isAdmin,
    uploadsError,
    onAuthExpired,
  } = useStoreContext();

  const {
    runtime,
    model,
    setModel,
    models,
    citationByMessage,
    activeCitationMessageId,
    selectedCitationIndex,
    showCitations,
    setSelectedCitationIndex,
    setShowCitations,
    setActiveCitationMessageId,
    handleRetryLast,
    handleLoadLastIntoComposer,
    composerInputRef,
    lastError,
    sessions,
    activeSessionId,
    loadingSessions,
    selectSession,
    createNewSession,
  } = useChatContext();

  const isRunning = useAssistantState(({ thread }) => thread?.isRunning ?? false);
  const currentThreadId = useAssistantState(
    ({ thread, threadListItem }) => threadListItem?.id ?? thread?.id ?? null,
  );
  const latestAssistantId = useAssistantState(({ thread }) => {
    const messages = thread?.messages ?? [];
    return [...messages].reverse().find((m) => m.role === "assistant")?.id ?? null;
  });
  const citationKey = activeSessionId || currentThreadId || "";
  const panelMessageId = activeCitationMessageId ?? latestAssistantId ?? null;
  const panelCitations =
    (panelMessageId && citationKey && citationByMessage[citationKey]?.[panelMessageId]) || [];
  const hasMessages = useAssistantState(({ thread }) => (thread?.messages?.length ?? 0) > 0);
  const [createStoreOpen, setCreateStoreOpen] = useState(false);
  const canUpload = Boolean(token && storeId);
  const uploadLimits = useMemo(() => getUploadLimits(), []);
  const fileAcceptValue = useMemo(
    () => buildAcceptValue(uploadLimits.allowedMimes),
    [uploadLimits.allowedMimes],
  );
  const [showAdminPanel, setShowAdminPanel] = useState(false);
  const [lastLoginEmail, setLastLoginEmail] = useState(() =>
    typeof window !== "undefined" ? sessionStorage.getItem("lastLoginEmail") || "" : "",
  );

  const handleFilesSafe = (files: FileList | null) => {
    if (!canUpload) {
      toast.error("Please log in and select a store first.");
      return;
    }
    handleFiles(files);
  };

  const handleAttachmentClick = (e: React.MouseEvent) => {
    if (!canUpload) {
      e.preventDefault();
      toast.error("Please log in and select a store first.");
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (!canUpload) {
      toast.error("Please log in and select a store first.");
      return;
    }
    handleFiles(e.dataTransfer.files);
  };

  const handleCloseAdmin = () => setShowAdminPanel(false);
  const handleLogout = () => {
    sessionStorage.removeItem("token");
    sessionStorage.removeItem("lastLoginEmail");
    setToken("");
    setShowAdminPanel(false);
  };

  React.useEffect(() => {
    if (!showAdminPanel) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        handleCloseAdmin();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [showAdminPanel]);

  return (
    <div className="flex h-screen bg-background text-foreground">
      <div className="w-80 border-r border-border bg-card p-4 overflow-y-auto">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <div className="h-9 w-9 rounded-full border border-border flex items-center justify-center bg-muted text-primary">
                <IconGlyph id={(settings.app_icon as IconId) || "sparkles"} className="w-5 h-5" />
              </div>
            <div>
              <h2 className="text-2xl font-bold">{settings.app_name || "RAG Assistant"}</h2>
              <p className="text-xs text-muted-foreground capitalize">{settings.theme_preset} theme</p>
            </div>
          </div>
          {isAdmin ? (
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={onOpenCustomizer}
                className="text-xs px-3 py-1.5 rounded-md border border-border hover:bg-muted"
              >
                Dev mode
              </button>
              <button
                type="button"
                onClick={() => setShowAdminPanel(true)}
                className="text-xs px-3 py-1.5 rounded-md border border-border hover:bg-muted text-red-600"
              >
                Admin
              </button>
            </div>
          ) : null}
        </div>
        {token ? (
          <div className="space-y-1 pb-4 border-b border-border mb-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-semibold text-foreground">Logged in</p>
                {lastLoginEmail ? (
                  <p className="text-xs text-muted-foreground">{lastLoginEmail}</p>
                ) : null}
              </div>
              <button
                type="button"
                onClick={handleLogout}
                className="text-xs px-3 py-1.5 rounded-md border border-border hover:bg-muted"
              >
                Log out
              </button>
            </div>
          </div>
        ) : (
          <LoginBox
            onToken={(t) => {
              setToken(t);
              setLastLoginEmail(sessionStorage.getItem("lastLoginEmail") || lastLoginEmail);
            }}
          />
        )}

        <div className="space-y-2 my-4">
          <select
            value={storeId ?? ""}
            onChange={(e) => setStoreId(e.target.value ? Number(e.target.value) : null)}
            className="w-full px-3 py-2 bg-background border border-input rounded-md"
            aria-label="Select a document store"
          >
            <option value="" disabled>
              Select a store
            </option>
            {stores.map((s) => (
              <option key={s.id} value={s.id}>
                {s.display_name}
              </option>
            ))}
          </select>
          <div className="space-y-1">
            <p className="text-sm font-semibold">Model</p>
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="w-full px-3 py-2 bg-background border border-input rounded-md"
              aria-label="Select a model"
            >
              {models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label}
                </option>
              ))}
            </select>
          </div>
          <button
            onClick={() => setCreateStoreOpen(true)}
            disabled={!token}
            title={!token ? "Please log in to create a store" : ""}
            className="w-full px-3 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            + New Store
          </button>
        </div>

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-muted-foreground">Chats</h3>
            <button
              type="button"
              onClick={() => createNewSession()}
              className="text-xs px-2 py-1 rounded-md border border-border hover:bg-muted"
            >
              + New
            </button>
          </div>
          {loadingSessions ? (
            <p className="text-xs text-muted-foreground">Loading chats…</p>
          ) : null}
          <div className="space-y-1 max-h-48 overflow-y-auto">
            {sessions.length === 0 ? (
              <p className="text-xs text-muted-foreground">No chats yet.</p>
            ) : (
              sessions.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => selectSession(s.id)}
                  className={`w-full text-left px-3 py-2 rounded-md border transition ${
                    activeSessionId === s.id ? "border-primary bg-primary/10" : "border-border hover:bg-muted"
                  }`}
                >
                  <div className="text-sm font-medium truncate">{s.title || "New chat"}</div>
                  <div className="text-xs text-muted-foreground">
                    {s.updated_at ? new Date(s.updated_at).toLocaleString() : "Just now"}
                  </div>
                </button>
              ))
            )}
          </div>
        </div>

        <div className="mt-6">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-muted-foreground">Documents</h3>
            <button
              className="text-xs text-muted-foreground hover:text-foreground"
              onClick={() => token && fetchDocuments()}
            >
              Refresh
            </button>
          </div>
          {uploadsError ? (
            <div className="text-xs text-red-500 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900 rounded p-2 mb-2">
              {uploadsError}
            </div>
          ) : null}
          <div className="space-y-2 max-h-48 overflow-y-auto">
            {documents.length === 0 ? (
              <p className="text-xs text-muted-foreground">No documents in this store.</p>
            ) : (
              documents.map((d) => (
                <div
                  key={d.id}
                  className="border border-border rounded-md p-2 text-xs flex items-center justify-between"
                  title={d.filename}
                >
                  <div className="flex-1">
                    <div className="font-semibold text-foreground truncate">
                      {d.display_name || d.filename}
                    </div>
                    <div className="text-muted-foreground truncate">
                      {d.status} • {(d.size_bytes / 1024).toFixed(1)} KB
                    </div>
                  </div>
                  <span className="text-muted-foreground ml-2">
                    {new Date(d.created_at).toLocaleDateString()}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>

        <CostPanel token={token} onAuthExpired={onAuthExpired} />
      </div>

      <div className="flex-1 flex flex-col relative">
        {lastError ? (
          <div className="absolute top-2 left-1/2 -translate-x-1/2 z-20 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900 text-red-700 dark:text-red-200 px-4 py-2 rounded shadow">
            {lastError}
          </div>
        ) : null}
        <ThreadPrimitive.Root className="flex flex-col h-full">
          <ThreadPrimitive.Viewport className="flex-1 overflow-y-auto px-4 py-6">
            <div className="max-w-3xl mx-auto space-y-4">
              {!hasMessages ? (
                <WelcomeCard
                  settings={settings}
                  onSelectPrompt={(prompt) => {
                    if (!prompt) return;
                    runtime.thread.composer.setText(prompt);
                    composerInputRef.current?.focus();
                  }}
                />
              ) : null}
              <ThreadPrimitive.Messages
                components={{
                  UserMessage: () => (
                    <MessagePrimitive.Root className="flex justify-end mb-4">
                      <div className="bg-primary text-primary-foreground px-4 py-3 rounded-2xl max-w-[80%]">
                        <MessagePrimitive.Content
                          components={{
                            Text: () => (
                              <p className="whitespace-pre-line">
                                <MessagePartPrimitive.Text />
                                <MessagePartPrimitive.InProgress>
                                  <span className="ml-1 font-sans">{" ●"}</span>
                                </MessagePartPrimitive.InProgress>
                              </p>
                            ),
                          }}
                        />
                      </div>
                    </MessagePrimitive.Root>
                  ),
                  AssistantMessage: () => (
                    <MessagePrimitive.Root className="flex justify-start mb-4">
                      <div className="bg-muted px-4 py-3 rounded-2xl max-w-[80%]">
                        <AssistantMessageContent
                          citationLookup={(threadId, messageId) =>
                            messageCitations(citationByMessage, activeSessionId || threadId || "", messageId)
                          }
                          setActiveMessageForPanel={setActiveCitationMessageId}
                          onSelectCitation={(index) => {
                            setSelectedCitationIndex(index);
                            setShowCitations(true);
                          }}
                        />
                      </div>
                    </MessagePrimitive.Root>
                  ),
                }}
              />
            </div>
          </ThreadPrimitive.Viewport>

          <div className="border-t border-border p-4">
            <div className="max-w-3xl mx-auto space-y-3">
              <ChatToolbar
                isRunning={isRunning}
                onStop={() => runtime.thread.cancelRun()}
                onRetry={handleRetryLast}
                onEditLast={handleLoadLastIntoComposer}
                model={model}
                setModel={setModel}
                models={models}
              />
              <ComposerPrimitive.Root
                className="flex gap-2 items-end bg-background border border-input rounded-lg p-2"
                onDragOver={(e) => e.preventDefault()}
                onDrop={handleDrop}
              >
                <ComposerPrimitive.Input
                  ref={composerInputRef}
                  placeholder="Ask a question about your documents..."
                  className="flex-1 bg-transparent px-2 py-2 text-sm outline-none resize-none"
                  autoFocus
                  rows={1}
                  onKeyDown={(e) => {
                    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
                      e.preventDefault();
                      runtime.thread.composer.send();
                    }
                    if (e.key === "Escape" && isRunning) {
                      e.preventDefault();
                      runtime.thread.cancelRun();
                    }
                  }}
                />
                <div className="flex flex-col gap-1">
                  <label
                    onClick={handleAttachmentClick}
                    className={`px-3 py-2 text-xs rounded-md border border-border hover:bg-muted cursor-pointer ${
                      !canUpload ? "opacity-50 cursor-not-allowed" : ""
                    }`}
                    aria-disabled={!canUpload}
                    title={!canUpload ? "Please log in and select a store to upload files" : ""}
                  >
                    <input
                      type="file"
                      accept={fileAcceptValue}
                      className="hidden"
                      multiple
                      disabled={!canUpload}
                      onChange={(e) => handleFilesSafe(e.target.files)}
                    />
                    Attach
                  </label>
                  {isRunning ? (
                    <ComposerPrimitive.Cancel className="px-4 py-2 bg-secondary text-secondary-foreground rounded-md hover:bg-secondary/90 text-sm font-medium">
                      Stop
                    </ComposerPrimitive.Cancel>
                  ) : (
                    <ComposerPrimitive.Send
                      disabled={!canUpload}
                      className="px-4 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90 text-sm font-medium disabled:opacity-50"
                    >
                      Send
                    </ComposerPrimitive.Send>
                  )}
                </div>
              </ComposerPrimitive.Root>
              <ComposerAttachments
                uploads={pendingUploads}
                onFileDrop={handleFilesSafe}
                canUpload={canUpload}
                uploadLimits={uploadLimits}
              />
            </div>
          </div>
        </ThreadPrimitive.Root>

        {panelCitations.length > 0 && (
          <button
            className="absolute bottom-24 right-6 px-4 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90 shadow-lg"
            onClick={() => setShowCitations(!showCitations)}
          >
            {showCitations ? "← Hide" : "Show"} Citations ({panelCitations.length})
          </button>
        )}
      </div>

      {showCitations && panelCitations.length > 0 && (
        <div className="w-80 border-l border-border bg-card p-4 overflow-y-auto">
          <CitationPanel citations={panelCitations} highlightIndex={selectedCitationIndex} />
        </div>
      )}

      <CreateStoreDialog
        open={createStoreOpen}
        onOpenChange={setCreateStoreOpen}
        token={token}
        onAuthExpired={onAuthExpired}
        onCreated={refreshStores}
      />
      {isAdmin && showAdminPanel ? (
        <div
          className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex justify-center items-center p-4"
          onClick={handleCloseAdmin}
          role="dialog"
          aria-modal="true"
        >
          <div
            className="bg-card border border-border rounded-lg shadow-xl w-full max-w-5xl max-h-[90vh] overflow-hidden flex flex-col relative"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex justify-between items-center p-4 border-b border-border">
              <h2 className="font-semibold text-lg">Admin Console</h2>
              <button
                onClick={handleCloseAdmin}
                className="text-muted-foreground hover:text-foreground p-1"
                aria-label="Close admin panel"
              >
                <span className="text-xl leading-none">&times;</span>
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-4">
              {token ? <AdminPanel token={token} onAuthExpired={onAuthExpired} /> : null}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
};
