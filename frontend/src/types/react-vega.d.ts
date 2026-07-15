declare module 'react-vega' {
  import * as React from 'react';

  export interface VegaEmbedProps extends React.HTMLAttributes<HTMLDivElement> {
    spec: Record<string, any> | string;
    options?: Record<string, any>;
    onEmbed?: (result: any) => void;
    onError?: (error: unknown) => void;
  }

  export const VegaEmbed: React.ForwardRefExoticComponent<
    VegaEmbedProps & React.RefAttributes<HTMLDivElement>
  >;
}
