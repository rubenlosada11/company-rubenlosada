export function Container({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <div className={`mx-auto w-[min(1120px,92vw)] ${className}`}>{children}</div>;
}
