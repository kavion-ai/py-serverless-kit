// Ready CORS configurations (the AWS console's JSON form) for the CORS editor.

export const CORS_EXAMPLES = [
  {
    id: "public-read",
    title: "Read from any website",
    description: "Any web page can download objects with fetch() or XMLHttpRequest (public assets, fonts, a CDN-like bucket).",
    rules: [{ AllowedHeaders: ["*"], AllowedMethods: ["GET", "HEAD"], AllowedOrigins: ["*"], ExposeHeaders: ["ETag"], MaxAgeSeconds: 3000 }],
  },
  {
    id: "one-origin-rw",
    title: "Read and upload from one website",
    description: "Pages on https://www.example.com can download, upload (presigned PUT or POST) and delete. Replace the origin with yours.",
    rules: [
      {
        AllowedHeaders: ["*"],
        AllowedMethods: ["GET", "HEAD", "PUT", "POST", "DELETE"],
        AllowedOrigins: ["https://www.example.com"],
        ExposeHeaders: ["ETag", "x-amz-version-id"],
        MaxAgeSeconds: 3000,
      },
    ],
  },
  {
    id: "presigned-upload",
    title: "Browser uploads with presigned URLs",
    description: "A web app on https://app.example.com uploads with presigned PUT URLs and reads the ETag (needed for multipart uploads).",
    rules: [
      { AllowedHeaders: ["*"], AllowedMethods: ["PUT"], AllowedOrigins: ["https://app.example.com"], ExposeHeaders: ["ETag"], MaxAgeSeconds: 3600 },
      { AllowedHeaders: [], AllowedMethods: ["GET"], AllowedOrigins: ["*"], ExposeHeaders: [] },
    ],
  },
  {
    id: "local-dev",
    title: "Local development",
    description: "Lets a development server on localhost call the bucket (http://localhost:3000 and http://localhost:5173).",
    rules: [
      {
        AllowedHeaders: ["*"],
        AllowedMethods: ["GET", "HEAD", "PUT", "POST", "DELETE"],
        AllowedOrigins: ["http://localhost:3000", "http://localhost:5173"],
        ExposeHeaders: ["ETag"],
      },
    ],
  },
];
