import { Navigate, Route, Routes } from "react-router";
import { PageTabs } from "../../components/ui";
import { BlogTab } from "./BlogTab";
import { BlogTagsTab } from "./BlogTagsTab";

/** Custodian › Blog's two parts: the articles, and the tags the custodian keeps for them (#1161). */
export function BlogPages() {
  return (
    <>
      <PageTabs
        label="The blog"
        tabs={[
          { to: "/custodian/blog", label: "Articles", end: true },
          { to: "/custodian/blog/tags", label: "Tags" },
        ]}
      />
      <Routes>
        <Route index element={<BlogTab />} />
        <Route path="tags" element={<BlogTagsTab />} />
        <Route path="*" element={<Navigate to="/custodian/blog" replace />} />
      </Routes>
    </>
  );
}
