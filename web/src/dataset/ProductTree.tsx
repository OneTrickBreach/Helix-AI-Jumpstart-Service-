/**
 * The bill of materials as an expandable finished-good → part tree.
 *
 * Each parent also gets a plain sentence ("each unit of FG-001 needs 3 of SA-001 and
 * 1 of SA-002"), because the tree tells a supply planner what it means and the
 * sentence tells everyone else.
 */

import { ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";

import { pluralize } from "../lib/datasetFormat";
import type { DatasetProducts } from "../lib/types";

function recipeSentence(parent: string, children: { sku_id: string; quantity_per_parent: number }[]) {
  if (!children.length) return `${parent} has no recorded parts.`;
  const parts = children.map((child) => `${child.quantity_per_parent} of ${child.sku_id}`);
  const joined =
    parts.length === 1
      ? parts[0]
      : `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`;
  return `Each unit of ${parent} needs ${joined}.`;
}

export default function ProductTree({ products }: { products: DatasetProducts }) {
  const [open, setOpen] = useState<string | null>(products.bom_tree[0]?.parent_sku_id ?? null);

  // Children that are themselves parents can be expanded one level further.
  const parents = new Map(products.bom_tree.map((entry) => [entry.parent_sku_id, entry.children]));

  return (
    <div className="grid gap-2">
      {products.bom_tree.map((entry) => {
        const isOpen = open === entry.parent_sku_id;
        return (
          <div key={entry.parent_sku_id} className="border border-line">
            <button
              type="button"
              onClick={() => setOpen(isOpen ? null : entry.parent_sku_id)}
              aria-expanded={isOpen}
              className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm font-semibold transition hover:bg-field focus:outline-none focus:ring-2 focus:ring-[#b8cfbd]"
            >
              <span className="flex items-center gap-2">
                {isOpen ? (
                  <ChevronDown className="h-4 w-4 shrink-0" />
                ) : (
                  <ChevronRight className="h-4 w-4 shrink-0" />
                )}
                {entry.parent_sku_id}
              </span>
              <span className="text-xs font-medium text-[#6d796f]">
                {pluralize(entry.children.length, "part")}
              </span>
            </button>
            {isOpen ? (
              <div className="border-t border-line px-3 py-3">
                <p className="text-sm leading-6">{recipeSentence(entry.parent_sku_id, entry.children)}</p>
                <ul className="mt-2 grid gap-1">
                  {entry.children.map((child) => {
                    const grandchildren = parents.get(child.sku_id);
                    return (
                      <li key={child.sku_id} className="text-sm">
                        <span className="inline-flex items-center gap-2">
                          <span className="text-[#9fb0a4]">└</span>
                          <span className="font-medium">{child.sku_id}</span>
                          <span className="text-[#536258]">
                            × {child.quantity_per_parent} per unit
                          </span>
                        </span>
                        {grandchildren?.length ? (
                          <ul className="ml-6 mt-1 grid gap-1 border-l border-line pl-3">
                            {grandchildren.map((grandchild) => (
                              <li key={grandchild.sku_id} className="text-xs text-[#536258]">
                                {grandchild.sku_id} × {grandchild.quantity_per_parent} per{" "}
                                {child.sku_id}
                              </li>
                            ))}
                          </ul>
                        ) : null}
                      </li>
                    );
                  })}
                </ul>
              </div>
            ) : null}
          </div>
        );
      })}
      {products.bom_tree_showing.truncated ? (
        <p className="text-xs text-[#6d796f]">{products.bom_tree_showing.note} parent products.</p>
      ) : null}
    </div>
  );
}
