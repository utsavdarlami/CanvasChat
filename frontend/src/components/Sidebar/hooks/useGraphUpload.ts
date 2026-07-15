import { useState } from 'react';
import { useAppStore } from '@/stores/appStore';
import { useGraphUploadActions } from '@/stores/graphStore';
import { useResetEntityState } from '@/stores/entityStore';
import { useResetChatSession } from '@/stores/chatStore';
import { readFileAsJSON, uploadImageFiles } from '@/services/api';
import { broadcastGraphData } from '@/services/yjsService';
import { convertEntitiesToGraphData, validateEntitiesData } from '@/utils/entitiesToGraphData';
import { clearAllCaches } from '@/components/EntityView/vegaSpecCache';
import { debugLogger } from '@/services/debugLogger';
import type { EntityRecord, GraphData } from '@/types/graph';

export interface UploadStatus {
  message: string;
  type: 'idle' | 'loading' | 'success' | 'error';
}

export function useGraphUpload() {
  const { setGraphData, setOriginalData, setLoading, setError } = useGraphUploadActions();
  const resetEntityState = useResetEntityState();
  const resetChatSession = useResetChatSession();

  const [entitiesFile, setEntitiesFile] = useState<File | null>(null);
  const [imageFiles, setImageFiles] = useState<File[]>([]);
  const [uploadStatus, setUploadStatus] = useState<UploadStatus>({
    message: '',
    type: 'idle'
  });
  const [analysisResult, setAnalysisResult] = useState<string>('');

  const handleEntitiesChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      setEntitiesFile(files[0]);
      setUploadStatus({ message: '', type: 'idle' });
      setAnalysisResult('');
    }
  };

  const handleImageFilesChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      setImageFiles(Array.from(files));
      setUploadStatus({ message: '', type: 'idle' });
    }
  };

  const finalizeUpload = (
    graphData: GraphData,
    entitiesData: EntityRecord[] | { analyzed_entities?: EntityRecord[] },
  ) => {
    resetEntityState();
    resetChatSession();
    clearAllCaches();
    useAppStore.getState().graph.clearGroupOverlays();

    const analyzedEntities = Array.isArray(entitiesData)
      ? entitiesData
      : entitiesData.analyzed_entities || [];
    setOriginalData(analyzedEntities);

    setGraphData(graphData);

    const storeGraph = useAppStore.getState().graph;
    broadcastGraphData({
      ...graphData,
      nodes: storeGraph.nodes,
    });

    useAppStore.getState().timeline.clearTimeline();
    useAppStore.getState().timeline.recordSnapshot('Initial layout', 'chat', storeGraph.nodes);
  };

  const handleUpload = async () => {
    if (!entitiesFile) {
      setUploadStatus({ message: 'Please select an entities file', type: 'error' });
      return;
    }

    setLoading(true);
    setUploadStatus({
      message: 'Loading entities and generating layout...',
      type: 'loading'
    });

    try {
      // If image files were selected, upload them to the backend first
      let imageUrlMap: Map<string, string> | null = null;
      if (imageFiles.length > 0) {
        setUploadStatus({ message: `Uploading ${imageFiles.length} image file(s)...`, type: 'loading' });
        imageUrlMap = await uploadImageFiles(imageFiles);
        console.log('[UploadSidebar] Uploaded images:', Object.fromEntries(imageUrlMap));
      }

      const entitiesData = await readFileAsJSON<EntityRecord[] | { analyzed_entities?: EntityRecord[] }>(entitiesFile);

      // Rewrite image entity values to use the uploaded static URLs
      if (imageUrlMap && imageUrlMap.size > 0) {
        const entities = Array.isArray(entitiesData)
          ? entitiesData
          : entitiesData.analyzed_entities || [];

        for (const entity of entities) {
          if (entity.type === 'image' && typeof entity.value === 'string') {
            // Match by filename (value could be just "the_godfather.jpg" or "posters/the_godfather.jpg")
            const filename = entity.value.split('/').pop() || entity.value;
            const url = imageUrlMap.get(filename);
            if (url) {
              entity.value = url;
            }
          }
        }
      }

      const validation = validateEntitiesData(entitiesData);
      if (!validation.valid) {
        throw new Error(validation.error || 'Invalid entities data');
      }

      console.log('[UploadSidebar] Entities-only mode: generating layout locally');
      const graphData = convertEntitiesToGraphData(entitiesData);

      const imageCount = graphData.nodes.filter(n => n.type === 'image').length;
      const html =
        `<strong>Entities loaded:</strong><br>` +
        `Nodes: ${graphData.nodes.length}${imageCount > 0 ? ` (${imageCount} images)` : ''}<br>` +
        `Layout: Grid-based distribution<br>` +
        `<em style="font-size: 0.9em;">No relationships file provided - entities distributed in grid pattern</em>`;

      setAnalysisResult(html);
      finalizeUpload(graphData, entitiesData);

      debugLogger.startSession({
        mode: 'entities-only',
        files: [entitiesFile.name],
        nodeCount: graphData.nodes.length,
      });

      setUploadStatus({
        message: 'Entities loaded! Visualization ready.',
        type: 'success'
      });
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      setError(errorMessage);
      setUploadStatus({
        message: `Load failed: ${errorMessage}`,
        type: 'error'
      });
      setAnalysisResult(
        `<strong>Error details:</strong><br>${errorMessage}`
      );
    } finally {
      setLoading(false);
    }
  };

  return {
    entitiesFile,
    imageFiles,
    uploadStatus,
    analysisResult,
    handleEntitiesChange,
    handleImageFilesChange,
    handleUpload,
    isUploadDisabled: !entitiesFile
  };
}
