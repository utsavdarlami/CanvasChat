import React from 'react';
import ReactMarkdown from 'react-markdown';
import type { Components } from 'react-markdown';

interface ChatMessageMarkdownProps {
  content: string;
}

function normalizeMarkdownInput(content: string): string {
  const normalized = content.replace(/\r\n/g, '\n');
  return normalized.includes('\n') ? normalized : normalized.replace(/\\n/g, '\n');
}

const markdownComponents: Components = {
  a: ({ node: _node, ...props }) => (
    <a {...props} target="_blank" rel="noreferrer noopener">
      {props.children}
    </a>
  ),
};

export const ChatMessageMarkdown: React.FC<ChatMessageMarkdownProps> = ({ content }) => {
  return (
    <div className="chat-markdown">
      <ReactMarkdown components={markdownComponents}>
        {normalizeMarkdownInput(content)}
      </ReactMarkdown>
    </div>
  );
};
