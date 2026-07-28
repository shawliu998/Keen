import type { HTMLAttributes, Key } from "react";

type MathMLProps = HTMLAttributes<MathMLElement> & { key?: Key };

declare global {
  namespace JSX {
    interface IntrinsicElements {
      math: MathMLProps;
      mi: MathMLProps;
      mn: MathMLProps;
      mo: MathMLProps;
      mrow: MathMLProps;
      mtable: MathMLProps;
      mtr: MathMLProps;
      mtd: MathMLProps;
    }
  }
}

export {};
