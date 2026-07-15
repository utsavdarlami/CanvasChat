import React from 'react';
import { formatFileSize } from '@/services/api';
import type { UploadStatus } from './hooks/useGraphUpload';

interface Props {
  entitiesFile: File | null;
  imageFiles: File[];
  uploadStatus: UploadStatus;
  handleEntitiesChange: (event: React.ChangeEvent<HTMLInputElement>) => void;
  handleImageFilesChange: (event: React.ChangeEvent<HTMLInputElement>) => void;
  handleUpload: () => void;
  isUploadDisabled: boolean;
}

export const FileUploadSection: React.FC<Props> = ({
  entitiesFile,
  imageFiles,
  uploadStatus,
  handleEntitiesChange,
  handleImageFilesChange,
  handleUpload,
  isUploadDisabled
}) => {
  return (
    <div className="upload-section">
      <label htmlFor="entities-input" className="upload-label">
        Entities file (JSON)
      </label>
      <input
        type="file"
        id="entities-input"
        accept=".json"
        onChange={handleEntitiesChange}
      />
      {entitiesFile && (
        <div className="file-info">
          <strong>Selected:</strong> {entitiesFile.name} ({formatFileSize(entitiesFile.size)})
        </div>
      )}

      <label htmlFor="images-input" className="upload-label">
        Image files (optional)
      </label>
      <input
        type="file"
        id="images-input"
        accept="image/*"
        multiple
        onChange={handleImageFilesChange}
      />
      {imageFiles.length > 0 && (
        <div className="file-info">
          <strong>Selected:</strong> {imageFiles.length} image{imageFiles.length !== 1 ? 's' : ''}{' '}
          ({formatFileSize(imageFiles.reduce((sum, f) => sum + f.size, 0))})
        </div>
      )}

      <button
        className="sidebar-btn sidebar-btn-primary"
        onClick={handleUpload}
        disabled={isUploadDisabled}
      >
        Load Entities
      </button>

      {uploadStatus.message && (
        <div className={`upload-status ${uploadStatus.type}`}>
          {uploadStatus.message}
        </div>
      )}
    </div>
  );
};
