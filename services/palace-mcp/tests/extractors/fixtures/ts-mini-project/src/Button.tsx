import React from "react";

interface ButtonProps {
  label: string;
  onClick: () => void;
}

export const Button: React.FC<ButtonProps> = (props) => (
  <button onClick={props.onClick}>{props.label}</button>
);
