// Type Definitions for CloudDrive Picker

export enum FileType {
  FOLDER = 'folder',
  IMAGE = 'image',
  VIDEO = 'video',
  DOCUMENT = 'document',
  PDF = 'pdf',
  SPREADSHEET = 'spreadsheet',
  OTHER = 'other'
}

export type ViewMode = 'grid' | 'list';

export interface CloudFile {
  id: string;
  name: string;
  type: FileType;
  size?: string;
  owner: string;
  modifiedAt: string;
  thumbnailUrl?: string;
  parentId: string | null; // null = root
}

export interface BreadcrumbItem {
  id: string | null;
  name: string;
}
