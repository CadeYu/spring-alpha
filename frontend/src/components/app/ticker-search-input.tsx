"use client";

import * as React from "react";
import { ArrowRight, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

type TickerSearchInputProps = {
  value: string;
  onValueChange: (value: string) => void;
  onSubmit: (ticker: string) => void;
  placeholder: string;
  buttonLabel: string;
  isSubmitting?: boolean;
  inputRef?: React.RefObject<HTMLInputElement | null>;
  wrapperClassName?: string;
  inputClassName?: string;
  buttonClassName?: string;
  inputProps?: Omit<
    React.ComponentProps<typeof Input>,
    "value" | "placeholder" | "ref"
  >;
};

export function TickerSearchInput({
  value,
  onValueChange,
  onSubmit,
  placeholder,
  buttonLabel,
  isSubmitting = false,
  inputRef,
  wrapperClassName,
  inputClassName,
  buttonClassName,
  inputProps,
}: TickerSearchInputProps) {
  const {
    onChange: externalOnChange,
    onKeyDown: externalOnKeyDown,
    className: externalClassName,
    ...restInputProps
  } = inputProps ?? {};

  const handleChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    onValueChange(event.currentTarget.value);
    externalOnChange?.(event);
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    externalOnKeyDown?.(event);
    if (event.defaultPrevented || event.key !== "Enter") {
      return;
    }
    onSubmit(event.currentTarget.value);
  };

  return (
    <div
      data-testid="ticker-input-group"
      className={cn(
        "flex h-14 items-stretch overflow-hidden rounded-lg border border-emerald-500/70 bg-slate-950 shadow-[0_0_0_1px_rgba(16,185,129,0.2)] focus-within:border-emerald-400 focus-within:ring-1 focus-within:ring-emerald-500/30",
        wrapperClassName,
      )}
    >
      <Input
        ref={inputRef}
        value={value}
        placeholder={placeholder}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        className={cn(
          "h-full flex-1 border-0 bg-transparent pr-16 text-xl font-bold tracking-widest text-emerald-200 shadow-none focus-visible:ring-0",
          externalClassName,
          inputClassName,
        )}
        {...restInputProps}
      />
      <Button
        type="button"
        aria-label={buttonLabel}
        onClick={() => onSubmit(inputRef?.current?.value ?? value)}
        disabled={isSubmitting}
        className={cn(
          "my-auto mr-2 h-10 w-10 shrink-0 rounded-lg bg-emerald-400 p-0 text-slate-950 shadow-lg shadow-emerald-950/40 hover:bg-emerald-300",
          buttonClassName,
        )}
      >
        {isSubmitting ? (
          <Loader2 className="h-5 w-5 animate-spin" />
        ) : (
          <ArrowRight className="h-5 w-5" />
        )}
      </Button>
    </div>
  );
}
