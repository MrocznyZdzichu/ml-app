export type OffsetPage<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
  has_next: boolean;
};

export type PageQuery = {
  limit?: number;
  offset?: number;
  search?: string;
};
