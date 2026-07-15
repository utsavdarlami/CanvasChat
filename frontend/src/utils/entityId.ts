export function getEntityId(node: { entity_id?: string; id?: string }): string {
  return node.entity_id || node.id || '';
}
