(vl-load-com)


(defun ASSET_GenerateGUID (/ obj guid)

  (setq obj
    (vlax-create-object "Scriptlet.TypeLib")
  )

  (setq guid
    (vlax-get-property obj 'GUID)
  )

  (vlax-release-object obj)

  (vl-string-subst
    ""
    "{"
    (vl-string-subst "" "}" guid)
  )
)


(defun ASSET_IsHexChar (ch)

  (if
    (vl-string-search
      (strcase ch)
      "0123456789ABCDEF"
    )
    T
    nil
  )
)


(defun ASSET_IsGUID (value / i valid)

  (setq valid T)

  (if
    (/= (strlen value) 36)

    nil

    (progn

      (if
        (not
          (and
            (= (substr value 9 1) "-")
            (= (substr value 14 1) "-")
            (= (substr value 19 1) "-")
            (= (substr value 24 1) "-")
          )
        )

        (setq valid nil)
      )

      (setq i 1)

      (while
        (and
          (<= i 36)
          valid
        )

        (if
          (and
            (/= i 9)
            (/= i 14)
            (/= i 19)
            (/= i 24)
          )

          (if
            (not
              (ASSET_IsHexChar
                (substr value i 1)
              )
            )

            (setq valid nil)
          )
        )

        (setq i
          (1+ i)
        )
      )

      valid
    )
  )
)


(defun ASSET_GetAttribute (obj tag / atts att result)

  (setq result nil)

  (if (= :vlax-true (vla-get-HasAttributes obj))

    (progn

      (setq atts
        (vlax-invoke obj 'GetAttributes)
      )

      (foreach att atts

        (if
          (= (strcase tag)
             (strcase (vla-get-TagString att)))

          (setq result att)
        )
      )
    )
  )

  result
)


(defun ASSET_CSVField (value)

  ;; Escape CSV field

  (if (not value)
    (setq value "")
  )

  (strcat
    "\""
    (vl-string-subst
      "\"\""
      "\""
      value
    )
    "\""
  )
)


(defun ASSET_CSVSplit
  (line / i ch field fields quoted)

  ;; Simple CSV parser supporting quoted fields
  ;; and escaped quotes.

  (setq i 1)
  (setq field "")
  (setq fields '())
  (setq quoted nil)

  (while (<= i (strlen line))

    (setq ch
      (substr line i 1)
    )

    (cond

      ;; Quote

      ((= ch "\"")

        (if quoted

          ;; Escaped quote ""

          (if
            (and
              (< i (strlen line))
              (= (substr line (1+ i) 1) "\"")
            )

            (progn

              (setq field
                (strcat field "\"")
              )

              (setq i
                (1+ i)
              )
            )

            (setq quoted nil)
          )

          (setq quoted T)
        )
      )

      ;; Comma outside quotes

      ((and
         (= ch ",")
         (not quoted)
       )

        (setq fields
          (append
            fields
            (list field)
          )
        )

        (setq field "")
      )

      ;; Normal character

      (T

        (setq field
          (strcat field ch)
        )
      )
    )

    (setq i
      (1+ i)
    )
  )

  ;; Last field

  (setq fields
    (append
      fields
      (list field)
    )
  )

  fields
)


(defun ASSET_CSVFind
  (rows asset_id / row result)

  (setq result nil)

  (foreach row rows

    (if
      (and
        (>= (length row) 3)
        (=

          (strcase
            (nth 0 row)
          )

          (strcase asset_id)
        )
      )

      (setq result row)
    )
  )

  result
)


(defun ASSET_CSVUpdate
  (rows asset_id kks asset_type / row result)

  (setq result '())

  (foreach row rows

    (if
      (and
        (>= (length row) 3)
        (=

          (strcase
            (nth 0 row)
          )

          (strcase asset_id)
        )
      )

      (setq result
        (append
          result
          (list
            (list
              asset_id
              kks
              asset_type
            )
          )
        )
      )

      (setq result
        (append
          result
          (list row)
        )
      )
    )
  )

  result
)


(defun ASSET_CSVRead
  (file / f line rows fields)

  (setq rows '())

  (if (findfile file)

    (progn

      (setq f
        (open file "r")
      )

      ;; Skip header

      (read-line f)

      ;; Read rows

      (while
        (setq line
          (read-line f)
        )

        (if
          (/= (vl-string-trim " \t\r\n" line) "")

          (progn

            (setq fields
              (ASSET_CSVSplit line)
            )

            (if
              (>= (length fields) 3)

              (setq rows
                (append
                  rows
                  (list fields)
                )
              )
            )
          )
        )
      )

      (close f)
    )
  )

  rows
)


(defun ASSET_CSVWrite
  (file rows / f row)

  (setq f
    (open file "w")
  )

  ;; Header

  (write-line
    "ASSET_ID,ASSET_KKS,ASSET_TYPE"
    f
  )

  ;; Data

  (foreach row rows

    (write-line

      (strcat

        (ASSET_CSVField
          (nth 0 row)
        )

        ","

        (ASSET_CSVField
          (nth 1 row)
        )

        ","

        (ASSET_CSVField
          (nth 2 row)
        )
      )

      f
    )
  )

  (close f)
)


(defun c:ASSET_CAD_EXPORT
  (/ ss i ent obj
     att_id att_kks att_type
     asset_id asset_kks asset_type
     file rows existing
     count_generated count_valid
     count_updated count_new count_assets)

  ;; -----------------------------------------
  ;; Find block references
  ;; -----------------------------------------

  (setq ss
    (ssget "_X" '((0 . "INSERT")))
  )

  (if (not ss)

    (alert
      "No block references found."
    )

    (progn

      ;; -----------------------------------------
      ;; Select / create CSV
      ;; -----------------------------------------

      (setq file
        (getfiled
          "Select or create Asset CSV"
          (strcat
            (getvar "DWGPREFIX")
            "Assets.csv"
          )
          "csv"
          1
        )
      )

      (if (not file)

        (alert
          "CSV export cancelled."
        )

        (progn

          ;; -----------------------------------------
          ;; Read existing CSV
          ;; -----------------------------------------

          (setq rows
            (ASSET_CSVRead
              file
            )
          )

          ;; -----------------------------------------
          ;; Counters
          ;; -----------------------------------------

          (setq i 0)
          (setq count_generated 0)
          (setq count_valid 0)
          (setq count_updated 0)
          (setq count_new 0)
          (setq count_assets 0)

          ;; -----------------------------------------
          ;; Process blocks
          ;; -----------------------------------------

          (while
            (< i (sslength ss))

            (setq ent
              (ssname ss i)
            )

            (setq obj
              (vlax-ename->vla-object ent)
            )

            ;; -----------------------------------------
            ;; Get attributes
            ;; -----------------------------------------

            (setq att_id
              (ASSET_GetAttribute
                obj
                "ASSET_ID"
              )
            )

            (setq att_kks
              (ASSET_GetAttribute
                obj
                "ASSET_KKS"
              )
            )

            (setq att_type
              (ASSET_GetAttribute
                obj
                "ASSET_TYPE"
              )
            )

            ;; -----------------------------------------
            ;; Only process blocks with ASSET_ID
            ;; -----------------------------------------

            (if att_id

              (progn

                (setq asset_id
                  (vla-get-TextString
                    att_id
                  )
                )

                (setq asset_kks "")
                (setq asset_type "")

                (if att_kks

                  (setq asset_kks
                    (vla-get-TextString
                      att_kks
                    )
                  )
                )

                (if att_type

                  (setq asset_type
                    (vla-get-TextString
                      att_type
                    )
                  )
                )

                ;; -----------------------------------
                ;; Validate ASSET_ID
                ;; -----------------------------------

                (if
                  (ASSET_IsGUID asset_id)

                  ;; Existing valid GUID

                  (setq count_valid
                    (1+ count_valid)
                  )

                  ;; Invalid GUID -> generate

                  (progn

                    (setq asset_id
                      (ASSET_GenerateGUID)
                    )

                    (vla-put-TextString
                      att_id
                      asset_id
                    )

                    (vla-Update att_id)
                    (vla-Update obj)

                    (setq count_generated
                      (1+ count_generated)
                    )
                  )
                )

                ;; -----------------------------------
                ;; Check CSV
                ;; -----------------------------------

                (setq existing
                  (ASSET_CSVFind
                    rows
                    asset_id
                  )
                )

                ;; -----------------------------------
                ;; Existing asset
                ;; -----------------------------------

                (if existing

                  (progn

                    (setq rows
                      (ASSET_CSVUpdate
                        rows
                        asset_id
                        asset_kks
                        asset_type
                      )
                    )

                    (setq count_updated
                      (1+ count_updated)
                    )
                  )

                  ;; ---------------------------------
                  ;; New asset
                  ;; ---------------------------------

                  (progn

                    (setq rows
                      (append
                        rows
                        (list
                          (list
                            asset_id
                            asset_kks
                            asset_type
                          )
                        )
                      )
                    )

                    (setq count_new
                      (1+ count_new)
                    )
                  )
                )

                (setq count_assets
                  (1+ count_assets)
                )
              )
            )

            (setq i
              (1+ i)
            )
          )

          ;; -----------------------------------------
          ;; Write CSV
          ;; -----------------------------------------

          (ASSET_CSVWrite
            file
            rows
          )

          ;; -----------------------------------------
          ;; Result
          ;; -----------------------------------------

          (alert

            (strcat

              "ASSET CSV export complete."

              "\n\nAssets processed: "
              (itoa count_assets)

              "\nNew IDs generated: "
              (itoa count_generated)

              "\nExisting IDs kept: "
              (itoa count_valid)

              "\nExisting CSV rows updated: "
              (itoa count_updated)

              "\nNew CSV rows added: "
              (itoa count_new)

              "\n\nCSV file:"
              "\n"
              file
            )
          )
        )
      )
    )
  )

  (princ)
)