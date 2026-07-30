import type { Conversation, ConversationSourceScope } from "@keen/api-client";

export type DurableConversationHandoff = {
  conversationId: string;
  question: string;
  sourceScope: ConversationSourceScope;
  scopeLabel: string;
  userMessageId: string;
  assistantMessageId: string;
  idempotencyKey: string;
  cancelIdempotencyKey: string;
  conversation: Conversation;
};

const PREFIX = "keen-durable-conversation-handoff:";

function key(conversationId: string): string {
  return `${PREFIX}${conversationId}`;
}

function parse(value: string | null, conversationId: string): DurableConversationHandoff | null {
  if (!value) return null;
  try {
    const candidate = JSON.parse(value) as Partial<DurableConversationHandoff>;
    const scope = candidate.sourceScope;
    if (
      candidate.conversationId !== conversationId
      || typeof candidate.question !== "string"
      || candidate.question.trim().length === 0
      || typeof candidate.scopeLabel !== "string"
      || typeof candidate.userMessageId !== "string"
      || typeof candidate.assistantMessageId !== "string"
      || typeof candidate.idempotencyKey !== "string"
      || typeof candidate.cancelIdempotencyKey !== "string"
      || !candidate.conversation
      || candidate.conversation.id !== conversationId
      || candidate.userMessageId === candidate.assistantMessageId
      || !scope
      || (scope.kind !== "all_indexed" && (scope.kind !== "course" || typeof scope.courseId !== "string"))
      || candidate.conversation.sourceScope.kind !== scope.kind
      || (scope.kind === "course" && (candidate.conversation.sourceScope.kind !== "course" || candidate.conversation.sourceScope.courseId !== scope.courseId))
    ) return null;
    return candidate as DurableConversationHandoff;
  } catch {
    return null;
  }
}

export function storeConversationHandoff(handoff: DurableConversationHandoff): void {
  sessionStorage.setItem(key(handoff.conversationId), JSON.stringify(handoff));
}

export function peekConversationHandoff(conversationId: string): DurableConversationHandoff | null {
  return parse(sessionStorage.getItem(key(conversationId)), conversationId);
}

export function consumeConversationHandoff(conversationId: string): DurableConversationHandoff | null {
  const storageKey = key(conversationId);
  const handoff = parse(sessionStorage.getItem(storageKey), conversationId);
  sessionStorage.removeItem(storageKey);
  return handoff;
}
