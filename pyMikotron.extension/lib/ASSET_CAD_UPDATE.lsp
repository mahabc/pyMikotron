(vl-load-com)


(defun ASSET_CSVSplit (line / values current quoted i char)

  (setq values '())
  (setq current "")
  (setq quoted nil)
  (setq i 1)

  (while (<= i (strlen line))

    (setq char (substr line i 1))

    (cond

      ((= char "\"")

        (if
          (and
            quoted
            (< i (strlen line))
            (= (substr line (+ i 1) 1) "\"")
          )

          (progn
            (setq current (strcat current "\""))
            (setq i (+ i 1))
          )

          (setq quoted (not quoted))
        )
      )

      ((and (= char ",") (not quoted))

        (setq values
          (append values (list current))
        )

        (setq current "")
      )

      (T

        (setq current
          (strcat current char)
        )
      )
    )

    (setq i (+ i 1))
  )

  (append values (list current))
)


(defun ASSET_CSVFindColumn (headers name / i found)

  (setq i 0)
  (setq found nil)

  (while (< i (length headers))

    (if
      (=
        (strcase
          (vl-string-trim " \"" (nth i headers))
        )
        (strcase name)
      )

      (setq found i)
    )

    (setq i (+ i 1))
  )

  found
)


(defun ASSET_GetAttribute (obj tag / att result)

  (setq result nil)

  (if (= (vla-get-HasAttributes obj) :vlax-true)

    (foreach att
      (vlax-invoke obj 'GetAttributes)

      (if
        (=
          (strcase (vla-get-TagString att))
          (strcase tag)
        )

        (setq result
          (vla-get-TextString att)
        )
      )
    )
  )

  result
)


(defun ASSET_SetAttribute (obj tag value / att found)

  (setq found nil)

  (if (= (vla-get-HasAttributes obj) :vlax-true)

    (foreach att
      (vlax-invoke obj 'GetAttributes)

      (if
        (=
          (strcase (vla-get-TagString att))
          (strcase tag)
        )

        (progn

          (vla-put-TextString att value)

          (setq found T)
        )
      )
    )
  )

  found
)


(defun ASSET_CSVRead (csv_file / file line headers rows)

  (setq file
    (open csv_file "r")
  )

  (if (not file)

    nil

    (progn

      (setq line
        (read-line file)
      )

      (if (not line)

        (progn
          (close file)
          nil
        )

        (progn

          (setq headers
            (ASSET_CSVSplit line)
          )

          (setq rows '())

          (while
            (setq line
              (read-line file)
            )

            (if (/= line "")

              (setq rows
                (append
                  rows
                  (list
                    (ASSET_CSVSplit line)
                  )
                )
              )
            )
          )

          (close file)

          (list headers rows)
        )
      )
    )
  )
)


(defun ASSET_CSVFindAsset
  (asset_id rows id_col kks_col type_col
   / row row_id result)

  (setq result nil)

  (foreach row rows

    (if (< id_col (length row))

      (progn

        (setq row_id
          (vl-string-trim
            " \""
            (nth id_col row)
          )
        )

        (if
          (=
            (strcase asset_id)
            (strcase row_id)
          )

          (setq result
            (list

              (if
                (< kks_col (length row))
                (vl-string-trim
                  " \""
                  (nth kks_col row)
                )
                ""
              )

              (if
                (< type_col (length row))
                (vl-string-trim
                  " \""
                  (nth type_col row)
                )
                ""
              )
            )
          )
        )
      )
    )
  )

  result
)


(defun c:ASSET_CAD_UPDATE
  (/ csv_file
     csv_data
     headers
     rows
     id_col
     kks_col
     type_col
     ss
     i
     obj
     asset_id
     asset_data
     updated
     not_found
     empty_id
     missing_id
     missing_kks
     missing_type
     kks_result
     type_result
     failed)

  (vl-load-com)

  (setq failed nil)


  ; ------------------------------------------------------
  ; Pick CSV database
  ; ------------------------------------------------------

  (setq csv_file
    (getfiled
      "Select Asset Database CSV"
      (getvar "DWGPREFIX")
      "csv"
      0
    )
  )


  ; ------------------------------------------------------
  ; Cancel
  ; ------------------------------------------------------

  (if (not csv_file)

    (setq failed T)

    (progn

      ; --------------------------------------------------
      ; Read CSV
      ; --------------------------------------------------

      (setq csv_data
        (ASSET_CSVRead csv_file)
      )


      (if (not csv_data)

        (setq failed T)

        (progn

          (setq headers (car csv_data))
          (setq rows (cadr csv_data))

          ; ----------------------------------------------
          ; Find columns
          ; ----------------------------------------------

          (setq id_col
            (ASSET_CSVFindColumn
              headers
              "ASSET_ID"
            )
          )

          (setq kks_col
            (ASSET_CSVFindColumn
              headers
              "ASSET_KKS"
            )
          )

          (setq type_col
            (ASSET_CSVFindColumn
              headers
              "ASSET_TYPE"
            )
          )


          ; ----------------------------------------------
          ; Validate columns
          ; ----------------------------------------------

          (if
            (or
              (null id_col)
              (null kks_col)
              (null type_col)
            )

            (setq failed T)

            (progn

              ; ------------------------------------------
              ; Get all blocks
              ; ------------------------------------------

              (setq ss
                (ssget "_X"
                  '(
                    (0 . "INSERT")
                  )
                )
              )


              (setq updated 0)
              (setq not_found 0)
              (setq empty_id 0)
              (setq missing_id 0)
              (setq missing_kks 0)
              (setq missing_type 0)


              ; ------------------------------------------
              ; Process blocks
              ; ------------------------------------------

              (if ss

                (progn

                  (setq i 0)

                  (while (< i (sslength ss))

                    (setq obj
                      (vlax-ename->vla-object
                        (ssname ss i)
                      )
                    )


                    (setq asset_id
                      (ASSET_GetAttribute
                        obj
                        "ASSET_ID"
                      )
                    )


                    (cond

                      ((null asset_id)

                        (setq missing_id
                          (+ missing_id 1)
                        )
                      )


                      ((= (vl-string-trim " " asset_id) "")

                        (setq empty_id
                          (+ empty_id 1)
                        )
                      )


                      (T

                        (setq asset_id
                          (vl-string-trim " " asset_id)
                        )


                        (setq asset_data
                          (ASSET_CSVFindAsset
                            asset_id
                            rows
                            id_col
                            kks_col
                            type_col
                          )
                        )


                        (if asset_data

                          (progn

                            (setq kks_result
                              (ASSET_SetAttribute
                                obj
                                "ASSET_KKS"
                                (car asset_data)
                              )
                            )


                            (setq type_result
                              (ASSET_SetAttribute
                                obj
                                "ASSET_TYPE"
                                (cadr asset_data)
                              )
                            )


                            (if kks_result
                              nil
                              (setq missing_kks
                                (+ missing_kks 1)
                              )
                            )


                            (if type_result
                              nil
                              (setq missing_type
                                (+ missing_type 1)
                              )
                            )


                            (if
                              (and
                                kks_result
                                type_result
                              )

                              (setq updated
                                (+ updated 1)
                              )
                            )
                          )

                          (setq not_found
                            (+ not_found 1)
                          )
                        )
                      )
                    )

                    (setq i (+ i 1))
                  )
                )
              )
            )
          )
        )
      )
    )
  )


  ; ------------------------------------------------------
  ; ONE FINAL ALERT
  ; ------------------------------------------------------

  (if failed

    (alert
      "ASSET_CAD_UPDATE FAILED.\n\n"
    )

    (alert
      (strcat
        "ASSET_CAD_UPDATE COMPLETE.\n\n"

        "Database:\n"
        csv_file
        "\n\n"

        "Blocks updated: "
        (itoa updated)
        "\n"

        "ASSET_ID not found: "
        (itoa not_found)
        "\n"

        "Empty ASSET_ID: "
        (itoa empty_id)
        "\n"

        "Missing ASSET_ID: "
        (itoa missing_id)
        "\n"

        "Missing ASSET_KKS: "
        (itoa missing_kks)
        "\n"

        "Missing ASSET_TYPE: "
        (itoa missing_type)
      )
    )
  )

  (princ)
)