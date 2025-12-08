import React, { useMemo } from "react";
import { MessagePartPrimitive, MessagePrimitive, useAssistantState } from "@assistant-ui/react";
import type { Citation } from "../CitationPanel";

type AssistantMessageContentProps = {
  citationLookup: (threadId: string, messageId: string) => Citation[];
  setActiveMessageForPanel: (id: string | null) => void;
  onSelectCitation: (index: number) => void;
};

export const AssistantMessageContent: React.FC<AssistantMessageContentProps> = ({
  citationLookup,
  onSelectCitation,
  setActiveMessageForPanel,
}) => {
  const messageId = useAssistantState(({ message }) => message.id);
  const threadId = useAssistantState(({ threadListItem }) => threadListItem?.id ?? "");
  const citations = useMemo(
    () => citationLookup(threadId, messageId),
    [citationLookup, messageId, threadId],
  );

  return (
    <>
      <MessagePrimitive.Content
        components={{
          Text: () => (
            <div className="prose prose-sm dark:prose-invert max-w-none">
              <MessagePartPrimitive.Text component="div" className="whitespace-pre-line" />
              <MessagePartPrimitive.InProgress>
                <span className="ml-1 font-sans">{" \u25CF"}</span>
              </MessagePartPrimitive.InProgress>
            </div>
          ),
        }}
      />
      {citations.some((c) => c.snippet) && (
        <div className="mt-4 pt-3 border-t border-border/50">
          <h4 className="text-xs font-semibold text-muted-foreground mb-2 text-right">Sources:</h4>
          <div className="flex flex-wrap gap-2 justify-end">
            {citations.map((c, idx) =>
              c.snippet ? (
                <button
                  key={c.sourceId || c.uri || c.filename || idx}
                  onClick={() => {
                    onSelectCitation(idx);
                    setActiveMessageForPanel(messageId);
                  }}
                  className="bg-muted-foreground/10 hover:bg-muted-foreground/20 text-xs px-3 py-1 rounded-md transition-colors"
                  aria-label={`View source ${idx + 1}`}
                  title="View source document chunk"
                >
                  [{idx + 1}]
                </button>
              ) : null,
            )}
          </div>
        </div>
      )}
    </>
  );
};
