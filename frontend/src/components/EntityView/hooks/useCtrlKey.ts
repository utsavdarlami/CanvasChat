/**
 * useCtrlKey - Tracks whether the Ctrl key is currently held down.
 *
 * Returns a boolean state value (for reactive prop updates)
 * that is true when Ctrl (or Meta on Mac) is pressed.
 */
import { useState, useEffect } from 'react';

export function useCtrlKey(): boolean {
  const [isCtrlHeld, setIsCtrlHeld] = useState(false);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Control' || e.key === 'Meta') {
        setIsCtrlHeld(true);
      }
    };

    const handleKeyUp = (e: KeyboardEvent) => {
      if (e.key === 'Control' || e.key === 'Meta') {
        setIsCtrlHeld(false);
      }
    };

    // Also reset on blur (user switches windows while holding Ctrl)
    const handleBlur = () => {
      setIsCtrlHeld(false);
    };

    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);
    window.addEventListener('blur', handleBlur);

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
      window.removeEventListener('blur', handleBlur);
    };
  }, []);

  return isCtrlHeld;
}
