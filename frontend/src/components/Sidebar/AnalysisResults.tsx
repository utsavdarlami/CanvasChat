import React from 'react';

interface Props {
  analysisResult: string;
}

const normalizeAnalysisText = (analysisResult: string): string => {
  return analysisResult.replace(/<br\s*\/?\s*>/gi, '\n').replace(/<[^>]*>/g, '').trim();
};

export const AnalysisResults: React.FC<Props> = ({ analysisResult }) => {
  if (!analysisResult) return null;

  return (
    <div className="analysis-result">
      <pre className="analysis-result-text">
        {normalizeAnalysisText(analysisResult)}
      </pre>
    </div>
  );
};
