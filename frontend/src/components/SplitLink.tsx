import { Link } from "react-router";
import { ActionMenu, MenuLink } from "./ActionMenu";

/**
 * A link with a chevron beside it: the link goes to the usual choice, the
 * chevron opens the other choices. Print uses it: ratings as your setting shows
 * them, or the other way for one print.
 */
export function SplitLink({ to, label, choices, menuLabel }: { to: string; label: string; choices: { to: string; label: string }[]; menuLabel: string }) {
  const part = "inline-flex min-h-10 items-center justify-center border border-ash bg-dusk text-sm hover:border-mist";
  return (
    <div className="flex">
      <Link to={to} className={`${part} flex-1 rounded-l-md px-4`}>
        {label}
      </Link>
      <ActionMenu label={menuLabel} trigger="▾" className="flex" buttonClassName={`${part} -ml-px rounded-r-md px-2.5 text-mist`} menuClassName="w-44">
        {choices.map((c) => (
          <MenuLink key={c.to} to={c.to}>
            {c.label}
          </MenuLink>
        ))}
      </ActionMenu>
    </div>
  );
}
